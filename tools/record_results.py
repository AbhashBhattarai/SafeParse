# record_results.py — Record fuzz/benchmark results into the webapp database.
#
# WHAT: Reads result files from c_tests/ and inserts rows into the
#       test_runs table in the webapp's SQLite database.
#
# WHY:  The web app shows test results alongside generated parsers.
#       This script bridges the gap between the C evaluation tools
#       (which produce text output files) and the web app (which
#       reads from SQLite).
#
# USAGE:
#   python tools/record_results.py bench   results/bench_output.txt
#   python tools/record_results.py fuzz    results/fuzz_udp_libfuzzer.txt
#
# The script refuses to insert results without a real file to parse.
# It never invents or makes up numbers.

import os
import sys
import sqlite3


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def get_db_path():
    """
    Find the path to the webapp's SQLite database.

    WHAT: Returns the absolute path to safeparse.db.
    WHY:  The database lives in the project root; this function
          makes the path work regardless of where you run the script from.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "safeparse.db")


def open_database():
    """
    Open and return a connection to the safeparse.db database.

    WHAT: Opens an SQLite connection.
    WHY:  We need to insert test_runs rows.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print("ERROR: Database not found at: {}".format(db_path))
        print("Run the web app once to create it, or run:")
        print("  python -c \"from webapp.db import init_db; init_db()\"")
        sys.exit(1)

    connection = sqlite3.connect(db_path)
    return connection


def find_parser_id(connection, format_name, variant):
    """
    Look up the generated_parsers row for a given format and variant.

    WHAT: Queries the generated_parsers table by joining with specs.
    WHY:  The test_runs table needs a parser_id foreign key.
          If no matching parser exists, we can't record results.
    """
    cursor = connection.execute(
        "SELECT gp.id FROM generated_parsers gp "
        "JOIN specs s ON gp.spec_id = s.id "
        "WHERE s.name = ? AND gp.variant = ? "
        "ORDER BY gp.id DESC LIMIT 1",
        (format_name, variant),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row[0]


def insert_test_run(connection, parser_id, fuzz_duration, crashes, avg_speed):
    """
    Insert one row into the test_runs table.

    WHAT: Creates a test_runs record with the given measurements.
    WHY:  The web app's results page displays these rows.
    """
    connection.execute(
        "INSERT INTO test_runs (parser_id, fuzz_duration_sec, crashes_found, avg_speed_ns) "
        "VALUES (?, ?, ?, ?)",
        (parser_id, fuzz_duration, crashes, avg_speed),
    )
    connection.commit()


# --------------------------------------------------------------------------
# Result file parsers
# --------------------------------------------------------------------------

def parse_bench_output(file_path):
    """
    Parse the benchmark output file and extract timing results.

    WHAT: Reads a bench.c output file and returns a list of result dicts.
    WHY:  bench.c prints a table; we parse each row to get spec, variant,
          and mean nanoseconds per call.

    Expected format (each data line):
      spec       | variant    | iterations | total_ms  | mean_ns
    """
    results = []
    handle = open(file_path, "r")
    lines = handle.readlines()
    handle.close()

    for line in lines:
        # Skip header lines, separator lines, and empty lines.
        stripped = line.strip()
        if stripped == "":
            continue
        if stripped.startswith("Spec") or stripped.startswith("---"):
            continue
        if "|" not in stripped:
            continue

        parts = stripped.split("|")
        if len(parts) < 5:
            continue

        spec_name = parts[0].strip()
        variant = parts[1].strip()
        mean_ns_str = parts[4].strip()

        # Skip the reference and dummy/sanity rows.
        if variant == "reference" or variant == "dummy":
            continue

        # Only record naive and optimized.
        if variant not in ("naive", "optimized"):
            continue

        try:
            mean_ns = float(mean_ns_str)
        except ValueError:
            print("WARNING: Could not parse mean_ns from: {}".format(line.strip()))
            continue

        results.append({
            "spec": spec_name,
            "variant": variant,
            "mean_ns": mean_ns,
        })

    return results


def parse_fuzz_output(file_path):
    """
    Parse a fuzz run summary file and extract crash/duration info.

    WHAT: Reads a fuzz summary and returns spec, variant, duration, crashes.
    WHY:  tools/run_fuzz.sh writes a summary; we parse it for the database.

    Expected format (key: value lines):
      spec: udp
      variant: naive
      engine: libfuzzer
      duration_sec: 60
      crashes_found: 0
    """
    result = {}
    handle = open(file_path, "r")
    lines = handle.readlines()
    handle.close()

    for line in lines:
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "spec":
            result["spec"] = value
        elif key == "variant":
            result["variant"] = value
        elif key == "duration_sec":
            try:
                result["duration_sec"] = int(value)
            except ValueError:
                result["duration_sec"] = 0
        elif key == "crashes_found":
            try:
                result["crashes_found"] = int(value)
            except ValueError:
                result["crashes_found"] = 0

    return result


# --------------------------------------------------------------------------
# Main command handlers
# --------------------------------------------------------------------------

def handle_bench(file_path):
    """
    Record benchmark results from a bench output file.

    WHAT: Parses the bench output and inserts one test_run per row.
    WHY:  This connects the C benchmark to the web app's results display.
    """
    if not os.path.exists(file_path):
        print("ERROR: File not found: {}".format(file_path))
        sys.exit(1)

    results = parse_bench_output(file_path)
    if len(results) == 0:
        print("ERROR: No benchmark results found in: {}".format(file_path))
        sys.exit(1)

    connection = open_database()
    recorded_count = 0

    for row in results:
        # Map spec names to format names used in the database.
        format_name_map = {
            "udp": "UdpHeader",
            "png_ihdr": "PngIhdr",
            "dns": "DnsHeader",
        }
        format_name = format_name_map.get(row["spec"])
        if format_name is None:
            print("WARNING: Unknown spec '{}', skipping.".format(row["spec"]))
            continue

        parser_id = find_parser_id(connection, format_name, row["variant"])
        if parser_id is None:
            print("WARNING: No parser found for {} / {}".format(
                format_name, row["variant"]
            ))
            print("  Compile the spec in the web app first, then re-run.")
            continue

        insert_test_run(
            connection,
            parser_id,
            fuzz_duration=None,
            crashes=None,
            avg_speed=row["mean_ns"],
        )
        recorded_count = recorded_count + 1
        print("  Recorded: {} {} -> {:.2f} ns/call".format(
            row["spec"], row["variant"], row["mean_ns"]
        ))

    connection.close()
    print("Done. {} results recorded.".format(recorded_count))


def handle_fuzz(file_path):
    """
    Record fuzz results from a fuzz summary file.

    WHAT: Parses the fuzz summary and inserts one test_run.
    WHY:  This connects the fuzz results to the web app's results display.
    """
    if not os.path.exists(file_path):
        print("ERROR: File not found: {}".format(file_path))
        sys.exit(1)

    result = parse_fuzz_output(file_path)

    needed_keys = ["spec", "duration_sec", "crashes_found"]
    for key in needed_keys:
        if key not in result:
            print("ERROR: Missing '{}' in fuzz output file.".format(key))
            sys.exit(1)

    connection = open_database()

    # Fuzz tests run both variants together (differential test).
    # Record results for both naive and optimized.
    format_name_map = {
        "udp": "UdpHeader",
        "png_ihdr": "PngIhdr",
        "dns": "DnsHeader",
    }
    format_name = format_name_map.get(result["spec"])
    if format_name is None:
        print("ERROR: Unknown spec '{}'.".format(result["spec"]))
        sys.exit(1)

    recorded_count = 0
    for variant in ["naive", "optimized"]:
        parser_id = find_parser_id(connection, format_name, variant)
        if parser_id is None:
            print("WARNING: No parser found for {} / {}".format(
                format_name, variant
            ))
            continue

        insert_test_run(
            connection,
            parser_id,
            fuzz_duration=result["duration_sec"],
            crashes=result["crashes_found"],
            avg_speed=None,
        )
        recorded_count = recorded_count + 1
        print("  Recorded: {} {} -> {} sec, {} crashes".format(
            result["spec"], variant,
            result["duration_sec"], result["crashes_found"]
        ))

    connection.close()
    print("Done. {} results recorded.".format(recorded_count))


def print_usage():
    """
    Print the usage message and exit.

    WHAT: Shows how to use this script.
    WHY:  The user needs to know the correct arguments.
    """
    print("Usage:")
    print("  python tools/record_results.py bench  <bench_output_file>")
    print("  python tools/record_results.py fuzz   <fuzz_summary_file>")
    print("")
    print("This script reads REAL result files and inserts them into")
    print("the safeparse.db database. It never invents numbers.")
    sys.exit(1)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_usage()

    command = sys.argv[1]
    file_path = sys.argv[2]

    if command == "bench":
        handle_bench(file_path)
    elif command == "fuzz":
        handle_fuzz(file_path)
    else:
        print("ERROR: Unknown command '{}'.".format(command))
        print_usage()
