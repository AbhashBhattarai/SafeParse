/*
 * SafeParse Evaluation Suite — Differential Fuzz Harness for DNS
 * Spec: specs/dns.spec
 * Target: libFuzzer
 *
 * WHAT: Differential fuzz harness comparing naive and optimized SafeParse
 *       DNS header parsers. Receives arbitrary byte sequences from libFuzzer
 *       and feeds them to both parsers.
 *
 * WHY:  Verifies memory safety (under AddressSanitizer and UndefinedBehaviorSanitizer)
 *       and confirms that the merged 12-byte bounds check in the optimized parser
 *       behaves identically to the 6 individual 2-byte checks in the naive parser.
 */

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "generated/dns_naive.h"
#include "generated/dns_optimized.h"

/*
 * Function: LLVMFuzzerTestOneInput
 * --------------------------------
 * WHAT: Entry point required by libFuzzer. Accepts a raw byte buffer and its
 *       size, invokes both naive_parse_DnsHeader and opt_parse_DnsHeader,
 *       and compares their return codes and parsed struct fields.
 *
 * WHY:  Detects subtle discrepancies between naive and optimized parsing.
 *       If return codes differ, or if both succeed but parsed header fields
 *       diverge, abort() is called immediately to log the crash artifact.
 *
 * Parameters:
 *   data - Pointer to input byte buffer provided by libFuzzer.
 *   size - Number of bytes in the buffer.
 *
 * Returns:
 *   Always 0, indicating the test case completed without libFuzzer errors.
 */
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    naive_DnsHeader naive_header;
    opt_DnsHeader opt_header;

    /* Initialize structs to zero to prevent uninitialized memory issues */
    memset(&naive_header, 0, sizeof(naive_header));
    memset(&opt_header, 0, sizeof(opt_header));

    /* Parse using both naive and optimized implementations */
    int naive_status = naive_parse_DnsHeader(data, size, &naive_header);
    int opt_status = opt_parse_DnsHeader(data, size, &opt_header);

    /* Check 1: Return codes must be identical */
    if (naive_status != opt_status) {
        fprintf(stderr,
                "Differential mismatch: DNS return codes differ!\n"
                "  Input size:       %zu bytes\n"
                "  Naive status:     %d\n"
                "  Optimized status: %d\n",
                size, naive_status, opt_status);
        abort();
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
            abort();
        }
    }

    return 0;
}
