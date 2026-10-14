#!/usr/bin/env bash
#
# run_fuzz.sh — Fuzz testing execution runner for SafeParse.
#
# WHAT: Automates compilation, corpus setup, fuzz execution, and crash reporting
#       for differential testing of SafeParse generated parsers against both
#       libFuzzer and AFL++ fuzzing engines.
#
# WHY:  Differential fuzzing compares the naive and optimized implementations
#       of each protocol parser (UDP, PNG IHDR, DNS) under thousands of mutated
#       inputs per second. Any behavioral divergence (differing return code or
#       mismatched parsed fields) or memory corruption is trapped and logged.
#
# USAGE:
#   tools/run_fuzz.sh <SPEC> <ENGINE> <DURATION_SEC>
#
# ARGUMENTS:
#   SPEC:         Protocol specification to test (udp | png_ihdr | dns)
#   ENGINE:       Fuzzing engine to use (libfuzzer | afl)
#   DURATION_SEC: Maximum execution time in seconds (e.g., 30, 60, 300)
#
# EXAMPLES:
#   tools/run_fuzz.sh udp libfuzzer 30
#   tools/run_fuzz.sh dns afl 60
#

set -u

# -----------------------------------------------------------------------------
# Function: print_usage
# WHAT: Displays command-line argument syntax and options.
# WHY:  Assists students and evaluators in running the script correctly.
# -----------------------------------------------------------------------------
print_usage() {
    echo "Usage: $0 <SPEC> <ENGINE> <DURATION_SEC>"
    echo ""
    echo "Arguments:"
    echo "  SPEC:         Protocol to fuzz. Supported: udp, png_ihdr, dns"
    echo "  ENGINE:       Fuzz engine. Supported: libfuzzer, afl"
    echo "  DURATION_SEC: Duration in seconds (positive integer, e.g. 30)"
    echo ""
    echo "Examples:"
    echo "  $0 udp libfuzzer 30"
    echo "  $0 png_ihdr libfuzzer 60"
    echo "  $0 dns afl 45"
    exit 1
}

# -----------------------------------------------------------------------------
# 1. Argument Parsing & Validation
# -----------------------------------------------------------------------------
if [ $# -lt 3 ]; then
    echo "ERROR: Missing required arguments." >&2
    print_usage
fi

SPEC="$1"
ENGINE="$2"
DURATION_SEC="$3"

# Validate SPEC
case "$SPEC" in
    udp|png_ihdr|dns)
        ;;
    *)
        echo "ERROR: Invalid SPEC '$SPEC'. Expected 'udp', 'png_ihdr', or 'dns'." >&2
        print_usage
        ;;
esac

# Validate ENGINE
case "$ENGINE" in
    libfuzzer|afl)
        ;;
    *)
        echo "ERROR: Invalid ENGINE '$ENGINE'. Expected 'libfuzzer' or 'afl'." >&2
        print_usage
        ;;
esac

# Validate DURATION_SEC is a positive integer
if ! [[ "$DURATION_SEC" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: DURATION_SEC must be a positive integer, got '$DURATION_SEC'." >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. Directory & Path Resolution
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
C_TESTS_DIR="$PROJECT_ROOT/c_tests"
CORPUS_DIR="$C_TESTS_DIR/corpus/$SPEC"
OUTPUT_DIR="$C_TESTS_DIR/fuzz_out/${SPEC}_${ENGINE}"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Ensure seed corpus is present; generate if missing
if [ ! -d "$CORPUS_DIR" ] || [ -z "$(ls -A "$CORPUS_DIR" 2>/dev/null)" ]; then
    echo "Corpus directory '$CORPUS_DIR' is missing or empty. Generating seed corpus..."
    if command -v python3 >/dev/null 2>&1; then
        python3 "$C_TESTS_DIR/create_corpus.py"
    elif command -v python >/dev/null 2>&1; then
        python "$C_TESTS_DIR/create_corpus.py"
    else
        echo "WARNING: Python not found; cannot auto-generate seed corpus." >&2
    fi
fi

echo "================================================================="
echo " SafeParse Differential Fuzzing Campaign"
echo "================================================================="
echo " Spec:       $SPEC"
echo " Engine:     $ENGINE"
echo " Duration:   ${DURATION_SEC}s"
echo " Corpus:     $CORPUS_DIR"
echo " Output Dir: $OUTPUT_DIR"
echo "================================================================="

CRASHES_FOUND=0
ACTUAL_DURATION="$DURATION_SEC"

# -----------------------------------------------------------------------------
# 3. Engine: libFuzzer
# -----------------------------------------------------------------------------
if [ "$ENGINE" = "libfuzzer" ]; then
    # Verify clang availability
    if ! command -v clang >/dev/null 2>&1; then
        echo "ERROR: 'clang' compiler not found in PATH." >&2
        echo "libFuzzer requires clang with compiler-rt built-in sanitizers." >&2
        exit 1
    fi

    HARNESS_SRC="$C_TESTS_DIR/fuzz_${SPEC}.c"
    if [ ! -f "$HARNESS_SRC" ]; then
        echo "ERROR: Harness source '$HARNESS_SRC' not found." >&2
        exit 1
    fi

    BINARY="$OUTPUT_DIR/fuzzer_${SPEC}"

    echo "==> [libFuzzer] Compiling harness with ASan and UBSan..."
    echo "    clang -std=c11 -Wall -Wextra -Werror -fsanitize=fuzzer,address,undefined -I\"$C_TESTS_DIR\" \"$HARNESS_SRC\" -o \"$BINARY\""

    clang -std=c11 -Wall -Wextra -Werror \
          -fsanitize=fuzzer,address,undefined \
          -I"$C_TESTS_DIR" \
          "$HARNESS_SRC" \
          -o "$BINARY"

    if [ $? -ne 0 ]; then
        echo "ERROR: Compilation failed for libFuzzer harness '$HARNESS_SRC'." >&2
        exit 1
    fi

    echo "==> [libFuzzer] Running fuzzer for ${DURATION_SEC} seconds..."
    START_TIME=$(date +%s)

    set +e
    "$BINARY" \
        -max_total_time="$DURATION_SEC" \
        -artifact_prefix="$OUTPUT_DIR/" \
        "$CORPUS_DIR" > "$OUTPUT_DIR/fuzz.log" 2>&1
    FUZZ_STATUS=$?
    set -e

    END_TIME=$(date +%s)
    ACTUAL_DURATION=$((END_TIME - START_TIME))
    if [ "$ACTUAL_DURATION" -le 0 ]; then
        ACTUAL_DURATION="$DURATION_SEC"
    fi

    # Count crash artifacts (libFuzzer prefixes artifacts with crash-, timeout-, leak-, oom-)
    CRASHES_FOUND=$(find "$OUTPUT_DIR" -maxdepth 1 -type f \( -name "crash-*" -o -name "leak-*" -o -name "timeout-*" -o -name "oom-*" \) 2>/dev/null | wc -l)

# -----------------------------------------------------------------------------
# 4. Engine: AFL++
# -----------------------------------------------------------------------------
elif [ "$ENGINE" = "afl" ]; then
    # Verify afl-gcc and afl-fuzz availability
    if ! command -v afl-gcc >/dev/null 2>&1; then
        echo "ERROR: 'afl-gcc' compiler not found in PATH." >&2
        echo "Please install AFL++ (apt install afl++ or build from source)." >&2
        exit 1
    fi

    if ! command -v afl-fuzz >/dev/null 2>&1; then
        echo "ERROR: 'afl-fuzz' executable not found in PATH." >&2
        exit 1
    fi

    HARNESS_SRC="$C_TESTS_DIR/afl_${SPEC}.c"
    if [ ! -f "$HARNESS_SRC" ]; then
        echo "ERROR: Harness source '$HARNESS_SRC' not found." >&2
        exit 1
    fi

    # Build binary outside the AFL output directory so AFL does not complain about non-empty dir
    BUILD_DIR="$C_TESTS_DIR/build"
    mkdir -p "$BUILD_DIR"
    BINARY="$BUILD_DIR/afl_${SPEC}"

    echo "==> [AFL++] Compiling harness with afl-gcc..."
    echo "    afl-gcc -std=c11 -Wall -Wextra -Werror -O2 -I\"$C_TESTS_DIR\" \"$HARNESS_SRC\" -o \"$BINARY\""

    afl-gcc -std=c11 -Wall -Wextra -Werror -O2 \
            -I"$C_TESTS_DIR" \
            "$HARNESS_SRC" \
            -o "$BINARY"

    if [ $? -ne 0 ]; then
        echo "ERROR: Compilation failed for AFL++ harness '$HARNESS_SRC'." >&2
        exit 1
    fi

    # AFL requires the output directory to not contain preexisting conflicting session files
    AFL_OUT_DIR="$OUTPUT_DIR/findings"
    mkdir -p "$AFL_OUT_DIR"

    echo "==> [AFL++] Running afl-fuzz for ${DURATION_SEC} seconds..."
    START_TIME=$(date +%s)

    set +e
    if command -v timeout >/dev/null 2>&1; then
        timeout --preserve-status "${DURATION_SEC}s" \
            afl-fuzz -i "$CORPUS_DIR" -o "$AFL_OUT_DIR" -- "$BINARY" > "$OUTPUT_DIR/fuzz.log" 2>&1
    else
        # Fallback to AFL -V flag for fixed duration
        afl-fuzz -V "$DURATION_SEC" -i "$CORPUS_DIR" -o "$AFL_OUT_DIR" -- "$BINARY" > "$OUTPUT_DIR/fuzz.log" 2>&1
    fi
    FUZZ_STATUS=$?
    set -e

    END_TIME=$(date +%s)
    ACTUAL_DURATION=$((END_TIME - START_TIME))
    if [ "$ACTUAL_DURATION" -le 0 ]; then
        ACTUAL_DURATION="$DURATION_SEC"
    fi

    # Count crashes inside AFL findings directories
    CRASHES_FOUND=0
    for CRASH_PATH in "$AFL_OUT_DIR"/crashes "$AFL_OUT_DIR"/*/crashes; do
        if [ -d "$CRASH_PATH" ]; then
            COUNT=$(find "$CRASH_PATH" -maxdepth 1 -type f ! -name "README.txt" 2>/dev/null | wc -l)
            CRASHES_FOUND=$((CRASHES_FOUND + COUNT))
        fi
    done
fi

# -----------------------------------------------------------------------------
# 5. Summary Generation & Database Compatibility
# -----------------------------------------------------------------------------
SUMMARY_FILE="$OUTPUT_DIR/summary.txt"

# Write key: value summary compatible with tools/record_results.py
cat << EOF > "$SUMMARY_FILE"
spec: $SPEC
variant: naive
engine: $ENGINE
duration_sec: $ACTUAL_DURATION
crashes_found: $CRASHES_FOUND
EOF

echo ""
echo "================================================================="
echo " SafeParse Fuzzing Results Summary"
echo "================================================================="
echo "  Spec:            $SPEC"
echo "  Variant:         differential (naive vs optimized)"
echo "  Engine:          $ENGINE"
echo "  Target Duration: ${DURATION_SEC}s"
echo "  Actual Duration: ${ACTUAL_DURATION}s"
echo "  Crashes Found:   $CRASHES_FOUND"
echo "  Output Dir:      $OUTPUT_DIR"
echo "  Log File:        $OUTPUT_DIR/fuzz.log"
echo "  Summary File:    $SUMMARY_FILE"
echo "================================================================="
echo ""
echo "To record these results in the SafeParse database, run:"
echo "  python tools/record_results.py fuzz \"$SUMMARY_FILE\""
echo "================================================================="

exit 0
