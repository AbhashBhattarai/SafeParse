/*
 * bench.c — SafeParse Performance Benchmark Harness
 *
 * IMPORTANT: This file uses clock_gettime(CLOCK_MONOTONIC, ...) and usleep(),
 * which are standard on POSIX systems (Linux/WSL). This benchmark harness is
 * designed to run in WSL or native Linux environments.
 *
 * WHAT: Runs high-iteration performance microbenchmarks comparing:
 *       1. Hand-written reference C parsers
 *       2. SafeParse naive (unoptimized) generated C parsers
 *       3. SafeParse optimized (merged bounds check) generated C parsers
 *       across three protocol specifications (UDP, PNG IHDR, and DNS).
 *       Also includes a deliberately slow dummy parser as a timing sanity check.
 *
 * WHY:  To empirically evaluate the performance overhead of automated bounds
 *       checks and validate the speedup achieved by SafeParse's AST bounds-check
 *       merging optimization against real hand-written C baselines.
 */

#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <unistd.h>

/* SafeParse auto-generated parser headers (naive and optimized) */
#include "udp_naive.h"
#include "udp_optimized.h"
#include "png_ihdr_naive.h"
#include "png_ihdr_optimized.h"
#include "dns_naive.h"
#include "dns_optimized.h"

/* Standard iteration counts */
#define WARMUP_ITERATIONS 1000
#define BENCH_ITERATIONS  1000000
#define DUMMY_ITERATIONS  100

/*
 * Global volatile sink to defeat dead code elimination.
 *
 * WHAT: Accumulates parser return values and field contents into a volatile variable.
 * WHY:  Under -O2 optimization, the compiler can detect if parser outputs are unused
 *       and eliminate the entire benchmark loop. Writing to a volatile variable forces
 *       the compiler to execute every single parser call and field extraction.
 */
static volatile uint64_t g_volatile_sink = 0;

/*
 * ref_UdpHeader — Representation of a parsed UDP header for the reference parser.
 *
 * WHAT: Holds the 4 16-bit header fields and a pointer/length for payload data.
 * WHY:  Provides a direct equivalent to naive_UdpHeader and opt_UdpHeader for fair comparison.
 */
typedef struct {
    uint16_t src_port;
    uint16_t dst_port;
    uint16_t length;
    uint16_t checksum;
    const uint8_t *payload;
    size_t payload_len;
} ref_UdpHeader;

/*
 * BenchmarkResult — Holds timing and iteration data for one benchmark run.
 *
 * WHAT: Stores specification name, variant name, iteration count, total wall-clock
 *       milliseconds, and computed mean nanoseconds per parse call.
 * WHY:  Decouples measurement collection from table printing and validation.
 */
typedef struct {
    const char *spec_name;
    const char *variant_name;
    size_t iterations;
    double total_ms;
    double mean_ns;
} BenchmarkResult;

/*
 * ref_parse_udp — Hand-written reference UDP parser.
 *
 * WHAT: Parses a raw buffer into a ref_UdpHeader struct using a single upfront
 *       bounds check for the 8-byte fixed header, reads the 4 u16 fields in
 *       network byte order (big-endian), verifies the payload length, and sets
 *       the payload pointer.
 * WHY:  Represents how an experienced C programmer writes an idiomatic, fast
 *       packet parser. This serves as the gold-standard baseline to determine
 *       whether SafeParse optimized parsers approach hand-written speed.
 */
int ref_parse_udp(const uint8_t *buf, size_t len, ref_UdpHeader *out) {
    /* Single bounds check for the 8-byte fixed header */
    if (len < 8) {
        return 1;
    }

    /* Read the four 16-bit fields in big-endian byte order */
    out->src_port = (uint16_t)(((uint16_t)buf[0] << 8) | buf[1]);
    out->dst_port = (uint16_t)(((uint16_t)buf[2] << 8) | buf[3]);
    out->length   = (uint16_t)(((uint16_t)buf[4] << 8) | buf[5]);
    out->checksum = (uint16_t)(((uint16_t)buf[6] << 8) | buf[7]);

    /* UDP datagram length must be at least 8 bytes (the header itself) */
    if (out->length < 8) {
        return 2;
    }

    /* Compute payload length and check remaining buffer bounds */
    size_t payload_len = (size_t)(out->length - 8);
    if (len - 8 < payload_len) {
        return 1;
    }

    out->payload = buf + 8;
    out->payload_len = payload_len;
    return 0;
}

/*
 * dummy_parse — Deliberately slow parser for timing calibration and sanity checking.
 *
 * WHAT: Ignores the input buffer and invokes usleep(1) to pause for ~1 microsecond.
 * WHY:  Acts as a timing sanity check. Because usleep(1) yields to the OS scheduler,
 *       each call will take roughly one scheduler quantum (>= 900,000 ns on Linux/WSL).
 *       Verifying this proves that clock_gettime(CLOCK_MONOTONIC) is functional and
 *       measuring actual wall-clock elapsed time rather than trivial hardware clock ticks.
 */
int dummy_parse(const uint8_t *buf, size_t len) {
    (void)buf;
    (void)len;
    usleep(1);
    return 0;
}

/*
 * timespec_diff_ns — Calculate elapsed nanoseconds between two timespec timestamps.
 *
 * WHAT: Computes (end.tv_sec - start.tv_sec) * 1e9 + (end.tv_nsec - start.tv_nsec).
 * WHY:  Converts the two-part struct timespec (seconds + nanoseconds) into a single
 *       continuous 64-bit floating point nanosecond duration for statistical calculations.
 */
static double timespec_diff_ns(const struct timespec *start, const struct timespec *end) {
    double seconds = (double)(end->tv_sec - start->tv_sec);
    double nanoseconds = (double)(end->tv_nsec - start->tv_nsec);
    return (seconds * 1.0e9) + nanoseconds;
}

/*
 * print_table_header — Print benchmark results table header and separator.
 *
 * WHAT: Outputs column titles (Spec, Variant, Iterations, Total(ms), Mean(ns))
 *       and markdown-compatible separator line to stdout.
 * WHY:  Ensures consistent, clean tabular output readable by both human examiners
 *       and automated processing scripts (e.g., tools/record_results.py).
 */
static void print_table_header(void) {
    printf("%-11s| %-11s| %-11s| %-10s| %-9s\n",
           "Spec", "Variant", "Iterations", "Total(ms)", "Mean(ns)");
    printf("-----------|------------|------------|-----------|----------\n");
}

/*
 * print_result_row — Print a single benchmark result row in table format.
 *
 * WHAT: Prints the spec, variant name, iteration count, total milliseconds,
 *       and nanoseconds per call with fixed-width column alignment.
 * WHY:  Produces standard formatted output line matching the required table layout.
 */
static void print_result_row(const BenchmarkResult *result) {
    printf("%-11s| %-11s| %-11zu| %-10.2f| %-9.2f\n",
           result->spec_name,
           result->variant_name,
           result->iterations,
           result->total_ms,
           result->mean_ns);
}

/*
 * bench_udp_reference — Benchmark the hand-written reference UDP parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of ref_parse_udp()
 *       using clock_gettime(CLOCK_MONOTONIC), feeding outputs to the volatile sink.
 * WHY:  Measures baseline performance of manual bounds-checked C code for UDP parsing.
 */
static BenchmarkResult bench_udp_reference(const uint8_t *packet, size_t length,
                                          size_t warmup_count, size_t run_count) {
    ref_UdpHeader out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = ref_parse_udp(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = ref_parse_udp(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "udp";
    result.variant_name = "reference";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_udp_naive — Benchmark SafeParse naive (unoptimized) UDP parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       naive_parse_UdpHeader(), feeding outputs to the volatile sink.
 * WHY:  Measures the unoptimized baseline where each header field performs
 *       an individual bounds check.
 */
static BenchmarkResult bench_udp_naive(const uint8_t *packet, size_t length,
                                      size_t warmup_count, size_t run_count) {
    naive_UdpHeader out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = naive_parse_UdpHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = naive_parse_UdpHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "udp";
    result.variant_name = "naive";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_udp_optimized — Benchmark SafeParse optimized UDP parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       opt_parse_UdpHeader(), feeding outputs to the volatile sink.
 * WHY:  Measures performance when fixed header bounds checks have been merged
 *       into a single 8-byte check by SafeParse's AST optimizer.
 */
static BenchmarkResult bench_udp_optimized(const uint8_t *packet, size_t length,
                                          size_t warmup_count, size_t run_count) {
    opt_UdpHeader out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = opt_parse_UdpHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = opt_parse_UdpHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.src_port;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "udp";
    result.variant_name = "optimized";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_png_ihdr_naive — Benchmark SafeParse naive PNG IHDR parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       naive_parse_PngIhdr(), feeding outputs to the volatile sink.
 * WHY:  Evaluates overhead when 7 separate bounds checks are executed for 13 bytes.
 */
static BenchmarkResult bench_png_ihdr_naive(const uint8_t *packet, size_t length,
                                           size_t warmup_count, size_t run_count) {
    naive_PngIhdr out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = naive_parse_PngIhdr(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.width;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = naive_parse_PngIhdr(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.width;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "png_ihdr";
    result.variant_name = "naive";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_png_ihdr_optimized — Benchmark SafeParse optimized PNG IHDR parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       opt_parse_PngIhdr(), feeding outputs to the volatile sink.
 * WHY:  Measures performance when 7 bounds checks are merged into 1 single
 *       13-byte check by the SafeParse optimizer.
 */
static BenchmarkResult bench_png_ihdr_optimized(const uint8_t *packet, size_t length,
                                               size_t warmup_count, size_t run_count) {
    opt_PngIhdr out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = opt_parse_PngIhdr(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.width;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = opt_parse_PngIhdr(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.width;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "png_ihdr";
    result.variant_name = "optimized";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_dns_naive — Benchmark SafeParse naive DNS header parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       naive_parse_DnsHeader(), feeding outputs to the volatile sink.
 * WHY:  Evaluates overhead when 6 consecutive u16 fields perform individual bounds checks.
 */
static BenchmarkResult bench_dns_naive(const uint8_t *packet, size_t length,
                                      size_t warmup_count, size_t run_count) {
    naive_DnsHeader out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = naive_parse_DnsHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.id;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = naive_parse_DnsHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.id;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "dns";
    result.variant_name = "naive";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_dns_optimized — Benchmark SafeParse optimized DNS header parser.
 *
 * WHAT: Executes warmup iterations, then times N=1,000,000 invocations of
 *       opt_parse_DnsHeader(), feeding outputs to the volatile sink.
 * WHY:  Demonstrates speedup when 6 bounds checks are merged into a single 12-byte check.
 */
static BenchmarkResult bench_dns_optimized(const uint8_t *packet, size_t length,
                                          size_t warmup_count, size_t run_count) {
    opt_DnsHeader out;
    struct timespec start_time;
    struct timespec end_time;

    /* Warmup phase (not timed) */
    for (size_t i = 0; i < warmup_count; i++) {
        int status = opt_parse_DnsHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.id;
    }

    /* Timed benchmark loop */
    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = opt_parse_DnsHeader(packet, length, &out);
        g_volatile_sink += (uint64_t)status + out.id;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "dns";
    result.variant_name = "optimized";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * bench_dummy — Run sanity check benchmark using dummy_parse.
 *
 * WHAT: Runs 100 iterations of dummy_parse() (which calls usleep(1)), measuring
 *       total elapsed wall-clock time with clock_gettime(CLOCK_MONOTONIC).
 * WHY:  Validates that timing infrastructure is accurate and reliable.
 *       On POSIX systems, usleep(1) takes at least the OS scheduling quantum
 *       (typically >= 900,000 ns per call).
 */
static BenchmarkResult bench_dummy(size_t run_count) {
    const uint8_t dummy_buf[1] = { 0 };
    struct timespec start_time;
    struct timespec end_time;

    clock_gettime(CLOCK_MONOTONIC, &start_time);
    for (size_t i = 0; i < run_count; i++) {
        int status = dummy_parse(dummy_buf, sizeof(dummy_buf));
        g_volatile_sink += (uint64_t)status;
    }
    clock_gettime(CLOCK_MONOTONIC, &end_time);

    double total_ns = timespec_diff_ns(&start_time, &end_time);
    BenchmarkResult result;
    result.spec_name = "dummy";
    result.variant_name = "dummy";
    result.iterations = run_count;
    result.total_ms = total_ns / 1.0e6;
    result.mean_ns = total_ns / (double)run_count;
    return result;
}

/*
 * main — Entry point for the SafeParse benchmark harness.
 *
 * WHAT: Prepares valid test packets for UDP, PNG IHDR, and DNS protocols,
 *       executes benchmarks across all variants (reference, naive, optimized)
 *       and the sanity-check dummy parser, prints the results in a formatted table,
 *       and confirms the timing sanity check threshold.
 * WHY:  Coordinates empirical performance evaluation for SafeParse research viva,
 *       outputting verifiable performance numbers with statistical consistency.
 */
int main(void) {
    /*
     * Valid 24-byte UDP packet:
     * - src_port: 1234 (0x04D2)
     * - dst_port: 80   (0x0050)
     * - length:   24   (0x0018: 8 header bytes + 16 payload bytes)
     * - checksum: 0x1A2B
     * - payload:  16 ASCII bytes
     */
    const uint8_t udp_packet[24] = {
        0x04, 0xd2,
        0x00, 0x50,
        0x00, 0x18,
        0x1a, 0x2b,
        'H', 'e', 'l', 'l', 'o', ' ', 'S', 'a',
        'f', 'e', 'P', 'a', 'r', 's', 'e', '!'
    };

    /*
     * Valid 13-byte PNG IHDR chunk:
     * - width:              1920 (0x00000780)
     * - height:             1080 (0x00000438)
     * - bit_depth:          8
     * - color_type:         6 (RGBA)
     * - compression_method: 0 (deflate)
     * - filter_method:      0 (adaptive)
     * - interlace_method:   0 (none)
     */
    const uint8_t png_ihdr_packet[13] = {
        0x00, 0x00, 0x07, 0x80,
        0x00, 0x00, 0x04, 0x38,
        0x08,
        0x06,
        0x00,
        0x00,
        0x00
    };

    /*
     * Valid 12-byte DNS header:
     * - id:      0x1234
     * - flags:   0x0100 (standard query)
     * - qdcount: 1
     * - ancount: 0
     * - nscount: 0
     * - arcount: 0
     */
    const uint8_t dns_packet[12] = {
        0x12, 0x34,
        0x01, 0x00,
        0x00, 0x01,
        0x00, 0x00,
        0x00, 0x00,
        0x00, 0x00
    };

    /* Print table column titles and divider line */
    print_table_header();

    /* Benchmark UDP parsers */
    BenchmarkResult res_udp_ref = bench_udp_reference(udp_packet, sizeof(udp_packet),
                                                      WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_udp_ref);

    BenchmarkResult res_udp_naive = bench_udp_naive(udp_packet, sizeof(udp_packet),
                                                    WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_udp_naive);

    BenchmarkResult res_udp_opt = bench_udp_optimized(udp_packet, sizeof(udp_packet),
                                                      WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_udp_opt);

    /* Benchmark PNG IHDR parsers */
    BenchmarkResult res_png_naive = bench_png_ihdr_naive(png_ihdr_packet, sizeof(png_ihdr_packet),
                                                         WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_png_naive);

    BenchmarkResult res_png_opt = bench_png_ihdr_optimized(png_ihdr_packet, sizeof(png_ihdr_packet),
                                                           WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_png_opt);

    /* Benchmark DNS parsers */
    BenchmarkResult res_dns_naive = bench_dns_naive(dns_packet, sizeof(dns_packet),
                                                    WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_dns_naive);

    BenchmarkResult res_dns_opt = bench_dns_optimized(dns_packet, sizeof(dns_packet),
                                                      WARMUP_ITERATIONS, BENCH_ITERATIONS);
    print_result_row(&res_dns_opt);

    /* Benchmark Dummy parser (timing sanity check) */
    BenchmarkResult res_dummy = bench_dummy(DUMMY_ITERATIONS);
    print_result_row(&res_dummy);

    /* Sanity check validation: dummy parser must take >= 900,000 ns per call */
    printf("\n--- Sanity Check ---\n");
    printf("Dummy parser mean per call: %.2f ns (expected >= 900000 ns)\n", res_dummy.mean_ns);
    if (res_dummy.mean_ns >= 900000.0) {
        printf("Result: PASS (timing resolution verified)\n");
    } else {
        printf("Result: NOTE (mean < 900000 ns; system timer resolution may vary)\n");
    }

    return EXIT_SUCCESS;
}
