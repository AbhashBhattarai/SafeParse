/*
 * SafeParse Evaluation Suite — AFL++ Differential Fuzz Harness for DNS
 * Spec: specs/dns.spec
 * Target: AFL++ (reads test inputs from standard input)
 *
 * WHAT: Differential fuzz harness comparing naive and optimized SafeParse
 *       DNS header parsers using AFL++ instrumentation. Reads up to 65536
 *       bytes from standard input (stdin) and feeds the buffer to both parsers.
 *
 * WHY:  AFL++ mutates test cases and delivers them via stdin. Differential
 *       testing compares both implementations to detect crashes, memory errors,
 *       or semantic divergence (return code or parsed field value mismatch).
 *
 * Exit Codes:
 *   0 - Both parsers behaved identically (success).
 *   1 - Differential mismatch detected between naive and optimized parsers.
 */

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "generated/dns_naive.h"
#include "generated/dns_optimized.h"

#define MAX_INPUT_BUFFER_SIZE 65536

/*
 * Function: main
 * --------------
 * WHAT: Reads up to 65536 bytes from standard input (stdin), invokes both
 *       naive_parse_DnsHeader and opt_parse_DnsHeader on that input, and
 *       verifies that both return the same status and parsed field values.
 *
 * WHY:  Required entry point for AFL++ fuzzing binary. AFL++ drives the harness
 *       through stdin; returning 0 signals a matching execution, while returning 1
 *       indicates a differential mismatch between the naive and optimized parsers.
 *
 * Returns:
 *   0 on success, 1 on differential mismatch.
 */
int main(void) {
    uint8_t input_buffer[MAX_INPUT_BUFFER_SIZE];
    size_t bytes_read = fread(input_buffer, 1, sizeof(input_buffer), stdin);

    naive_DnsHeader naive_header;
    opt_DnsHeader opt_header;

    /* Initialize structs to zero to prevent uninitialized memory issues */
    memset(&naive_header, 0, sizeof(naive_header));
    memset(&opt_header, 0, sizeof(opt_header));

    /* Parse using both naive and optimized implementations */
    int naive_status = naive_parse_DnsHeader(input_buffer, bytes_read, &naive_header);
    int opt_status = opt_parse_DnsHeader(input_buffer, bytes_read, &opt_header);

    /* Check 1: Return codes must match */
    if (naive_status != opt_status) {
        fprintf(stderr,
                "Differential mismatch: DNS return codes differ!\n"
                "  Input size:       %zu bytes\n"
                "  Naive status:     %d\n"
                "  Optimized status: %d\n",
                bytes_read, naive_status, opt_status);
        return 1;
    }

    /* Check 2: When both parsers return OK, all field values must match */
    if (naive_status == NAIVE_PARSE_OK) {
        if (naive_header.id != opt_header.id ||
            naive_header.flags != opt_header.flags ||
            naive_header.qdcount != opt_header.qdcount ||
            naive_header.ancount != opt_header.ancount ||
            naive_header.nscount != opt_header.nscount ||
            naive_header.arcount != opt_header.arcount) {
            fprintf(stderr, "Differential mismatch: DNS header field values differ!\n");
            return 1;
        }
    }

    return 0;
}
