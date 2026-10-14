# SafeParse

**SafeParse** is a domain-specific compiler and web application written in Python 3.11. It reads declarative specifications describing binary packet and file formats (such as UDP headers, DNS packets, and PNG chunks) and generates memory-safe, zero-copy C parsing code.

SafeParse explores a compiler optimization research question:
* **Naive Mode:** Emits an explicit bounds check before *every single* field read.
* **Optimized Mode:** Uses a field-grouping optimizer pass to coalesce consecutive fixed-size field reads into a *single* combined bounds check, preserving separate checks for variable-length fields (`bytes[...]`).

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Command-Line Interface (CLI)](#command-line-interface-cli)
5. [Web Application](#web-application)
   - [Starting the Server](#starting-the-server)
   - [Creating an Administrator](#creating-an-administrator)
   - [Web App Features](#web-app-features)
6. [Testing](#testing)
7. [C Evaluation & Benchmarking (WSL / Linux)](#c-evaluation--benchmarking-wsl--linux)
8. [Worked Example (Spec & Generated C)](#worked-example-spec--generated-c)
9. [What Is and Isn't Implemented](#what-is-and-isnt-implemented)

---

## Project Overview

Binary parsing in C is historically prone to buffer over-reads, integer underflows, and arithmetic wrapping vulnerabilities. SafeParse prevents these vulnerabilities by generating C code that:
1. Enforces **strict unsigned bounds checks** (`offset > len` and `len - offset < size`) before dereferencing any byte.
2. Emits **underflow guards** on variable-length fields (e.g. `out->length >= 8` for `bytes[length - 8]`) returning `PARSE_ERR_BAD_LENGTH` if the computed size would underflow.
3. Automatically handles endianness (big-endian and little-endian) using bitwise shifts.
4. Generates standard C structs containing exact-width integer types (`stdint.h`) and pointer/length pairs for variable payloads.

---

## Project Structure

```text
SafeParse/
├── conftest.py             # Pytest root configuration
├── safeparse/              # Core compiler package
│   ├── __init__.py         # Package marker
│   ├── __main__.py         # Entry point for python -m safeparse
│   ├── lexer.py            # Hand-written tokenizer (tokens with line numbers)
│   ├── parser.py           # Hand-written recursive-descent parser (AST generation)
│   ├── checker.py          # Semantic checker (validates types, uniqueness, references)
│   ├── optimizer.py        # Optimizer pass (groups contiguous fixed-size fields)
│   ├── codegen.py          # C code generator (naive and optimized modes)
│   ├── compiler.py         # Top-level API: compile_spec(spec_text, mode)
│   └── cli.py              # Command-line interface with argument parsing
├── specs/                  # Example binary format specifications
│   ├── udp.spec            # UDP header with dependent-length payload
│   ├── png_ihdr.spec       # PNG IHDR chunk (13 fixed-size bytes)
│   └── dns.spec            # DNS header (12 bytes of fixed u16 fields)
├── webapp/                 # Flask web application layer
│   ├── __init__.py         # Package marker
│   ├── app.py              # Flask routes and authentication
│   ├── db.py               # SQLite database connection helpers
│   ├── schema.sql          # Database schema (users, specs, parsers, test_runs)
│   ├── create_admin.py     # Interactive CLI tool to create/promote admin accounts
│   ├── static/
│   │   └── style.css       # Clean, dependency-free CSS styling
│   └── templates/
│       ├── base.html       # Base layout with navigation and role badge
│       ├── register.html   # User registration page
│       ├── login.html      # User login page
│       ├── compile.html    # Spec input form and side-by-side C viewer
│       ├── history.html    # Past specifications list (developer/admin scoped)
│       ├── history_detail.html # Detail view of a saved spec & parsers
│       └── results.html    # Fuzzing and benchmark evaluation table
├── c_tests/                # C evaluation, harnesses, and benchmarks
│   ├── generated/          # Auto-generated C headers (naive & optimized)
│   ├── corpus/             # Seed corpus for libFuzzer & AFL++
│   ├── generate_headers.py # Script generating C headers from specs
│   ├── create_corpus.py    # Seed generator script using struct.pack
│   ├── run_cases.c         # C correctness harness (truncations, bad lengths, fuzz)
│   ├── bench.c             # Performance microbenchmark with volatile sink
│   ├── fuzz_*.c            # libFuzzer differential test harnesses (udp, png, dns)
│   ├── afl_*.c             # AFL++ differential test harnesses (udp, png, dns)
│   └── Makefile            # C build configuration (-O2, sanitizers)
├── tools/                  # Automation and evaluation scripts
│   ├── run_fuzz.sh         # Automated fuzzing pipeline script (WSL/Linux)
│   └── record_results.py   # Ingests bench/fuzz output into safeparse.db
├── tests/                  # Test suites (72 passing unit & integration tests)
│   ├── test_lexer.py       # Lexer unit tests
│   ├── test_parser.py      # Recursive-descent parser unit tests
│   ├── test_checker.py     # Semantic analyzer unit tests
│   ├── test_optimizer.py   # Optimizer grouping tests
│   ├── test_codegen.py     # C code generation tests
│   ├── test_compiler.py    # End-to-end compiler integration tests
│   └── test_webapp.py      # Web app integration tests (test client & temp DB)
├── README.md               # Project documentation and manual
├── LEARNING_GUIDE.md       # Student rebuild guide, theory, and 25 viva questions
└── AUDIT_REPORT.md         # Independent code and safety audit report
```

---

## Installation

SafeParse requires **Python 3.11** and minimal dependencies:

```bash
# Clone or navigate to the project directory
cd D:\SafeParse

# Install dependencies
pip install flask pytest
```

No external parsing libraries (like PLY or Lark) or ORMs are used. Everything in the compiler and database layer is built using Python standard library primitives (`sqlite3`, `werkzeug.security`).

---

## Command-Line Interface (CLI)

The compiler can be invoked directly from the terminal via Python module execution:

```bash
# 1. Compile in default naive mode (prints C code to stdout)
python -m safeparse specs/udp.spec

# 2. Compile in optimized mode (merges fixed-size bounds checks)
python -m safeparse specs/udp.spec --mode optimized

# 3. Save the generated C parser to a file
python -m safeparse specs/udp.spec --mode optimized --output udp_parser.c
```

### Supported Types in Spec Files
* `u8` — 8-bit unsigned integer (1 byte).
* `u16` — 16-bit unsigned integer, big-endian (2 bytes).
* `u32` — 32-bit unsigned integer, big-endian (4 bytes).
* `u16le` — 16-bit unsigned integer, little-endian (2 bytes).
* `u32le` — 32-bit unsigned integer, little-endian (4 bytes).
* `bytes[EXPR]` — variable-length slice, where `EXPR` can be a constant integer, a prior integer field name, or an arithmetic expression like `length - 8`.

---

## Web Application

The SafeParse web app allows developers to test specs in the browser, inspect the generated naive and optimized C parsers side by side, and review past compilation history stored in an SQLite database.

### Database Schema
The database (`safeparse.db`) consists of 4 relational tables:
1. `users` — `id`, `username` (UNIQUE), `password_hash`, `role` (`'developer'` or `'admin'`), `created_at`.
2. `specs` — `id`, `user_id` (FK -> users), `name`, `spec_text`, `created_at`.
3. `generated_parsers` — `id`, `spec_id` (FK -> specs), `variant` (`'naive'` or `'optimized'`), `c_code`.
4. `test_runs` — `id`, `parser_id` (FK -> generated_parsers), `fuzz_duration_sec`, `crashes_found`, `avg_speed_ns`.

### Starting the Server

```bash
python webapp/app.py
```
The server will start on `http://127.0.0.1:5000`.

### Creating an Administrator
New users registered through the web interface receive the `'developer'` role. To create an administrator or promote an existing user:

```bash
python webapp/create_admin.py
```
Follow the interactive prompt:
```text
--- SafeParse Administrator Account Setup ---
Enter admin username: admin
Enter admin password: <type password>
Admin user 'admin' created successfully!
```

### Web App Features
* **Authentication:** Password hashing via `werkzeug.security` (`scrypt` / `pbkdf2`), session-based login, and a custom `@login_required` decorator.
* **Compile Page:** Prefilled with the UDP specification. On submission, the server invokes `compile_spec()` for both `naive` and `optimized` variants, records the spec and both C outputs in SQLite, and displays both parsers side by side in formatted `<pre>` blocks.
* **Error Handling:** Invalid specs display line-numbered errors (e.g. forward references, unknown types) on the page; invalid specs are never saved to the database.
* **History Page (Role-Based Access):**
  * Developers only see their own specifications.
  * Administrators see all specifications from all users, along with the author's username.
  * Direct access to `/history/<spec_id>` is protected; attempting to view another developer's parser returns `403 Forbidden`.
* **Results Page:** Displays test run data joined across `test_runs`, `generated_parsers`, and `specs`. When no evaluations have been recorded, displays `"No evaluation results recorded yet"`. No synthetic or fake benchmark numbers are ever seeded.

---

## Testing

SafeParse includes unit and integration tests using `pytest` covering all compiler stages and the web app:

```bash
# Run the complete test suite (72 tests)
python -m pytest tests/ -v
```

All 72 tests pass cleanly with 100% success:
* `tests/test_lexer.py` (10 tests): Tokenization, multi-line tracking, whitespace, comments, symbols.
* `tests/test_parser.py` (12 tests): Grammar parsing, AST nodes, binary expressions, little-endian types.
* `tests/test_checker.py` (12 tests): Semantic validations, duplicate rejection, forward-reference checks.
* `tests/test_optimizer.py` (7 tests): FieldGroup generation, contiguous merging, bytes[] isolation.
* `tests/test_codegen.py` (13 tests): C struct generation, bounds check assertions, endianness bitshifts.
* `tests/test_compiler.py` (10 tests): End-to-end compilation pipeline, protocol spec verification.
* `tests/test_webapp.py` (7 tests): Registration, password hashing, sessions, compilation, history isolation, RBAC.

---

## C Evaluation & Benchmarking (WSL / Linux)

The research evaluation infrastructure measures parsing throughput and verifies differential memory safety between naive (per-field check) and optimized (merged check) parsers.

Because libFuzzer and AFL++ require LLVM and POSIX primitives, the C evaluation tools are designed to run in **Linux / WSL2 (Ubuntu)**.

### 1. Generating C Headers from Specs
Before compiling C tests, generate the naive and optimized headers:
```bash
python c_tests/generate_headers.py
```
This produces 6 header files in `c_tests/generated/` (`udp_naive.h`, `udp_optimized.h`, `png_ihdr_naive.h`, `png_ihdr_optimized.h`, `dns_naive.h`, `dns_optimized.h`).

### 2. Running the Correctness & Differential Test Harness
Tests valid packets, all truncations (prefix lengths 0..N), invalid dependent lengths, and 1,000 differential random inputs with AddressSanitizer and UndefinedBehaviorSanitizer:
```bash
cd c_tests
make run_cases
./run_cases
```

### 3. Running Microbenchmarks
Evaluates high-iteration throughput (1,000,000 iterations per parser with warm-up and volatile sink under `-O2`):
```bash
cd c_tests
make bench
./bench
```

### 4. Running Differential Fuzzing
Differential fuzzing feeds identical mutated inputs to both parser variants and asserts identical behavior:
```bash
# Using libFuzzer (clang):
bash tools/run_fuzz.sh udp libfuzzer 60

# Using AFL++ (afl-fuzz):
bash tools/run_fuzz.sh udp afl 60
```

### 5. Ingesting Real Results into the Web App Database
```bash
# Record benchmark output into safeparse.db:
python tools/record_results.py bench results/bench_output.txt

# Record fuzz run summary into safeparse.db:
python tools/record_results.py fuzz c_tests/fuzz_out/udp_libfuzzer/summary.txt
```
The results will immediately display in the web app under the **Evaluation Results** (`/results`) tab.

---

## Worked Example (Spec & Generated C)

### Input: `specs/udp.spec`
```text
format UdpHeader {
    src_port:  u16
    dst_port:  u16
    length:    u16
    checksum:  u16
    payload:   bytes[length - 8]
}
```

### Output: Naive Generated C Parser
In naive mode, notice how every field has its own separate bounds check:
```c
#include <stdint.h>
#include <stddef.h>

/* Return codes for the parse function */
#define PARSE_OK             0
#define PARSE_ERR_TOO_SHORT  1
#define PARSE_ERR_BAD_LENGTH 2

/* Parsed representation of UdpHeader */
typedef struct {
    uint16_t src_port;
    uint16_t dst_port;
    uint16_t length;
    uint16_t checksum;
    const uint8_t *payload;
    size_t payload_len;
} UdpHeader;

/* Parse raw bytes into a UdpHeader struct */
int parse_UdpHeader(const uint8_t *buf, size_t len, UdpHeader *out) {
    size_t offset = 0;

    /* Bounds check for: src_port (2 bytes) */
    if (offset > len) return PARSE_ERR_TOO_SHORT;
    if (len - offset < 2) return PARSE_ERR_TOO_SHORT;
    out->src_port = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
    offset += 2;

    /* Bounds check for: dst_port (2 bytes) */
    if (offset > len) return PARSE_ERR_TOO_SHORT;
    if (len - offset < 2) return PARSE_ERR_TOO_SHORT;
    out->dst_port = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
    offset += 2;

    /* Bounds check for: length (2 bytes) */
    if (offset > len) return PARSE_ERR_TOO_SHORT;
    if (len - offset < 2) return PARSE_ERR_TOO_SHORT;
    out->length = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
    offset += 2;

    /* Bounds check for: checksum (2 bytes) */
    if (offset > len) return PARSE_ERR_TOO_SHORT;
    if (len - offset < 2) return PARSE_ERR_TOO_SHORT;
    out->checksum = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
    offset += 2;

    /* Read variable-length field: payload */
    {
        if (!(out->length >= 8)) return PARSE_ERR_BAD_LENGTH;
        size_t payload_len = (size_t)((out->length - 8));
        if (offset > len) return PARSE_ERR_TOO_SHORT;
        if (len - offset < payload_len) return PARSE_ERR_TOO_SHORT;
        out->payload = buf + offset;
        out->payload_len = payload_len;
        offset += payload_len;
    }

    return PARSE_OK;
}
```

### Output: Optimized Generated C Parser
In optimized mode, the 4 fixed-size `u16` fields (8 bytes total) are coalesced into a single bounds check:
```c
/* Bounds check for: src_port, dst_port, length, checksum (8 bytes) */
if (offset > len) return PARSE_ERR_TOO_SHORT;
if (len - offset < 8) return PARSE_ERR_TOO_SHORT;
/* Read field: src_port (u16) */
out->src_port = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
offset += 2;
/* Read field: dst_port (u16) */
out->dst_port = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
offset += 2;
/* Read field: length (u16) */
out->length = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
offset += 2;
/* Read field: checksum (u16) */
out->checksum = (uint16_t)(((uint16_t)buf[offset] << 8) | buf[offset + 1]);
offset += 2;

/* Read variable-length field: payload */
{
    if (!(out->length >= 8)) return PARSE_ERR_BAD_LENGTH;
    size_t payload_len = (size_t)((out->length - 8));
    if (offset > len) return PARSE_ERR_TOO_SHORT;
    if (len - offset < payload_len) return PARSE_ERR_TOO_SHORT;
    out->payload = buf + offset;
    out->payload_len = payload_len;
    offset += payload_len;
}
```

---

## What Is and Isn't Implemented

### Fully Implemented
* **Hand-written Lexer:** Tokenizes source specifications with line numbers and skips comments.
* **Hand-written Recursive-Descent Parser:** Builds an AST without external parser generators.
* **Semantic Analyzer:** Detects duplicates, unknown types, self-references, forward references, and non-integer length dependencies with exact line numbers.
* **Optimizer Pass:** Accurately groups contiguous fixed-size fields and separates runtime dynamic `bytes[]` fields.
* **C Code Generator:** Supports naive and optimized modes, big and little endianness, overflow-safe arithmetic checks, and underflow guards.
* **Flask Web Application:** Complete authentication, registration, session management, side-by-side C code viewing, developer history isolation, administrator cross-user inspection, and evaluation results viewing.
* **SQLite Relational Layer:** Parameterized SQL queries, foreign key enforcement, automatic connection pooling/teardown.
* **Automated Python Test Suite:** 72 unit and integration tests passing with 100% success across all stages.
* **C Correctness Harness (`c_tests/run_cases.c`):** Tests valid packets, all truncations, bad dependent lengths, and random fuzz cases with AddressSanitizer and UndefinedBehaviorSanitizer.
* **Differential Fuzzing Harnesses:** libFuzzer (`fuzz_*.c`) and AFL++ (`afl_*.c`) harnesses comparing naive vs optimized execution on identical inputs, with seed corpus generation.
* **Performance Microbenchmark (`c_tests/bench.c`):** High-iteration benchmark with warm-up, volatile sink, and nanosecond timing under `-O2`.
* **Evaluation Pipeline & Database Ingestion:** `tools/run_fuzz.sh` automation script and `tools/record_results.py` for ingesting real benchmark and fuzz metrics into `safeparse.db`.

### Platform Notes & Target Environments
* **Python Compiler & Web App:** Fully portable; works natively on Windows, macOS, and Linux with Python 3.11+.
* **C Evaluation Harnesses:** The correctness harness, libFuzzer/AFL++ harnesses, and `bench.c` use POSIX/Linux APIs (`clock_gettime`, `unistd.h`) and LLVM sanitizers. They are designed to run under **Linux / WSL2 (Ubuntu)** with `clang`, `gcc`, and `afl++`.
* **Results Display:** The `/results` page displays data from the `test_runs` SQLite table. In a fresh clone before running benchmarks under Linux, it cleanly shows an empty state rather than inventing synthetic numbers.
