# SafeParse — Linux & WSL Evaluation Manual

This guide explains how to compile, benchmark, and fuzz SafeParse's generated C parsers on native Linux (or WSL2 Ubuntu), and how to record empirical results into the web application's SQLite database.

---

## 1. Prerequisites (Linux Packages)

On your Linux system (Ubuntu/Debian), open a terminal and install the C compilers, build tools, LLVM/clang, AFL++, and Python:

```bash
sudo apt update
sudo apt install -y build-essential clang afl++ python3 python3-pip python3-venv make git
```

*(If using Fedora: `sudo dnf install -y gcc clang afl-fuzz python3 python3-pip make git`)*

---

## 2. Setting Up the Python Environment

Navigate to the project root and create a virtual environment:

```bash
cd SafeParse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Verify that the Python test suite passes cleanly:

```bash
pytest -v
```
*(All 72 tests should pass with 100% success).*

---

## 3. Step-by-Step C Evaluation Workflow

### Step 1: Generate C Headers from Specifications
Before compiling C test harnesses, run the header generator:

```bash
python3 c_tests/generate_headers.py
```
This reads `specs/udp.spec`, `specs/png_ihdr.spec`, and `specs/dns.spec` and outputs 6 header files into `c_tests/generated/`:
* `udp_naive.h` & `udp_optimized.h`
* `png_ihdr_naive.h` & `png_ihdr_optimized.h`
* `dns_naive.h` & `dns_optimized.h`

---

### Step 2: Run the C Correctness Harness (with Sanitizers)
Compile and run the correctness test harness under **AddressSanitizer (ASan)** and **UndefinedBehaviorSanitizer (UBSan)**:

```bash
cd c_tests
make run_cases
./run_cases
```

**What this verifies:**
1. **Valid Packets:** Asserts both naive and optimized parsers return `PARSE_OK` and decode identical struct field values.
2. **Buffer Truncation:** Feeds all prefix lengths (0 up to full length) and asserts both variants safely reject truncated data with `PARSE_ERR_TOO_SHORT`.
3. **Invalid Dependent Lengths:** Feeds packets with payload lengths $< 8$ and asserts both variants reject with `PARSE_ERR_BAD_LENGTH`.
4. **Differential Fuzzing:** Feeds 1,000 randomized binary buffers to both variants and asserts identical return codes and struct field values with 0 crashes.

---

### Step 3: Run High-Iteration Microbenchmarks
Compile the benchmark binary under `-O2` (without sanitizers for fair CPU timing) and execute 1,000,000 iterations per parser:

```bash
make bench
mkdir -p ../results
./bench | tee ../results/bench_output.txt
cd ..
```

**What this measures:**
* Wall-clock elapsed time (`ms`) and mean nanoseconds per call (`ns`) across:
  * Hand-written reference UDP parser
  * Naive generated UDP parser (bounds check before every field)
  * Optimized generated UDP parser (merged 8-byte bounds check)
  * Naive vs optimized PNG IHDR parsers
  * Naive vs optimized DNS parsers
* Timing calibration sanity check using a deliberately delayed dummy parser.

---

### Step 4: Run Differential Fuzzing (libFuzzer & AFL++)

SafeParse provides an automated fuzzing script in `tools/run_fuzz.sh`.

#### A. Running with libFuzzer (Clang + ASan + UBSan)
Run a 60-second differential fuzzing job on the UDP protocol:

```bash
bash tools/run_fuzz.sh udp libfuzzer 60
```
*(You can also run for `png_ihdr` or `dns`).*

#### B. Running with AFL++
```bash
bash tools/run_fuzz.sh udp afl 60
```

The script stores artifacts, crash logs, and execution summaries in `c_tests/fuzz_out/<spec>_<engine>/summary.txt`.

---

### Step 5: Ingest Real Results into the SQLite Database

To display real empirical benchmark and fuzzing results on the Flask web app's `/results` page:

```bash
# 1. Ingest benchmark metrics:
python3 tools/record_results.py bench results/bench_output.txt

# 2. Ingest fuzzing metrics:
python3 tools/record_results.py fuzz c_tests/fuzz_out/udp_libfuzzer/summary.txt
```

---

### Step 6: View the Results in the Web App

Start the Flask development server:

```bash
python3 webapp/app.py
```

1. Open your browser to `http://127.0.0.1:5000`.
2. Log in with your developer account or create an admin account using:
   ```bash
   python3 webapp/create_admin.py
   ```
3. Navigate to **Evaluation Results** (`/results`) to view the real timing and fuzzing metrics recorded from your Linux system.

---

## 4. Key Viva Questions on Evaluation

* **Q: Why are microbenchmarks compiled with `-O2` without sanitizers, while the correctness harness uses `-fsanitize=address,undefined`?**
  * *Answer:* Sanitizers insert runtime instrumentation that adds overhead (typically 2x–3x slowdown). For microbenchmarking, we want to measure production execution speed under standard compiler optimization (`-O2`). For correctness and fuzzing, sanitizers are essential to detect hidden out-of-bounds reads or undefined behaviors.
* **Q: How does `bench.c` prevent the compiler from optimizing away the benchmark loop?**
  * *Answer:* All parser return codes and struct fields are written to a global `volatile uint64_t g_volatile_sink`. The C standard requires that writes to volatile variables cannot be eliminated by compiler dead-code elimination.
* **Q: Why does differential fuzzing compare two parsers instead of checking just one?**
  * *Answer:* In differential fuzzing, the naive parser serves as the oracle for the optimized parser. Because naive mode performs simple, obviously correct bounds checks before every read, asserting identical outputs on millions of mutated inputs proves that check coalescing introduced zero regression.
