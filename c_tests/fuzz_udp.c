/*
 * SafeParse Evaluation Suite — Differential Fuzz Harness for UDP
 * Spec: specs/udp.spec
 * Target: libFuzzer
 *
 * WHAT: Differential fuzz harness comparing naive and optimized SafeParse
 *       UDP parsers. Receives arbitrary byte sequences from libFuzzer and feeds
 *       them to both parsers.
 *
 * WHY:  Verifies memory safety (under AddressSanitizer and UndefinedBehaviorSanitizer)
 *       and ensures that the optimized parser behaves identically to the naive
 *       reference parser across all possible inputs.
 */

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "generated/udp_naive.h"
#include "generated/udp_optimized.h"

/*
 * Function: LLVMFuzzerTestOneInput
 * --------------------------------
 * WHAT: Entry point required by libFuzzer. Accepts a raw byte buffer and its
 *       size, invokes both naive_parse_UdpHeader and opt_parse_UdpHeader,
 *       and compares their results.
 *
 * WHY:  In differential fuzzing, any divergence between naive and optimized
 *       behavior indicates a compiler optimization bug or bounds check error.
 *       If return codes differ, or if both succeed but field values differ,
 *       abort() is called immediately to generate a crash artifact for analysis.
 *
 * Parameters:
 *   data - Pointer to input byte buffer provided by libFuzzer.
 *   size - Number of bytes in the buffer.
 *
 * Returns:
 *   Always 0, indicating the test case completed without libFuzzer errors.
 */
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    naive_UdpHeader naive_header;
    opt_UdpHeader opt_header;

    /* Initialize structs to zero to prevent uninitialized memory issues */
    memset(&naive_header, 0, sizeof(naive_header));
    memset(&opt_header, 0, sizeof(opt_header));

    /* Parse using both naive and optimized implementations */
    int naive_status = naive_parse_UdpHeader(data, size, &naive_header);
    int opt_status = opt_parse_UdpHeader(data, size, &opt_header);

    /* Check 1: Return codes must be identical */
    if (naive_status != opt_status) {
        fprintf(stderr,
                "Differential mismatch: return codes differ!\n"
                "  Input size:       %zu bytes\n"
                "  Naive status:     %d\n"
                "  Optimized status: %d\n",
                size, naive_status, opt_status);
        abort();
    }

    /* Check 2: When both parsers return OK, all field values must match */
    if (naive_status == NAIVE_PARSE_OK) {
        if (naive_header.src_port != opt_header.src_port) {
            fprintf(stderr,
                    "Differential mismatch: src_port differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.src_port,
                    (unsigned int)opt_header.src_port);
            abort();
        }

        if (naive_header.dst_port != opt_header.dst_port) {
            fprintf(stderr,
                    "Differential mismatch: dst_port differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.dst_port,
                    (unsigned int)opt_header.dst_port);
            abort();
        }

        if (naive_header.length != opt_header.length) {
            fprintf(stderr,
                    "Differential mismatch: length differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.length,
                    (unsigned int)opt_header.length);
            abort();
        }

        if (naive_header.checksum != opt_header.checksum) {
            fprintf(stderr,
                    "Differential mismatch: checksum differs (naive=0x%04X, opt=0x%04X)\n",
                    (unsigned int)naive_header.checksum,
                    (unsigned int)opt_header.checksum);
            abort();
        }

        if (naive_header.payload_len != opt_header.payload_len) {
            fprintf(stderr,
                    "Differential mismatch: payload_len differs (naive=%zu, opt=%zu)\n",
                    naive_header.payload_len,
                    opt_header.payload_len);
            abort();
        }

        if (naive_header.payload_len > 0) {
            if (memcmp(naive_header.payload, opt_header.payload, naive_header.payload_len) != 0) {
                fprintf(stderr, "Differential mismatch: payload content differs!\n");
                abort();
            }
        }
    }

    return 0;
}
