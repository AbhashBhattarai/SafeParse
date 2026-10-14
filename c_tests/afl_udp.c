/*
 * SafeParse Evaluation Suite — AFL++ Differential Fuzz Harness for UDP
 * Spec: specs/udp.spec
 * Target: AFL++ (reads test inputs from standard input)
 *
 * WHAT: Differential fuzz harness comparing naive and optimized SafeParse
 *       UDP parsers using AFL++ instrumentation. Reads up to 65536 bytes
 *       from standard input (stdin) and feeds the buffer to both parsers.
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

#include "generated/udp_naive.h"
#include "generated/udp_optimized.h"

#define MAX_INPUT_BUFFER_SIZE 65536

/*
 * Function: main
 * --------------
 * WHAT: Reads up to 65536 bytes from standard input (stdin), invokes both
 *       naive_parse_UdpHeader and opt_parse_UdpHeader on that input, and
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

    naive_UdpHeader naive_header;
    opt_UdpHeader opt_header;

    /* Initialize structs to zero to prevent uninitialized memory issues */
    memset(&naive_header, 0, sizeof(naive_header));
    memset(&opt_header, 0, sizeof(opt_header));

    /* Parse using both naive and optimized implementations */
    int naive_status = naive_parse_UdpHeader(input_buffer, bytes_read, &naive_header);
    int opt_status = opt_parse_UdpHeader(input_buffer, bytes_read, &opt_header);

    /* Check 1: Return codes must match */
    if (naive_status != opt_status) {
        fprintf(stderr,
                "Differential mismatch: UDP return codes differ!\n"
                "  Input size:       %zu bytes\n"
                "  Naive status:     %d\n"
                "  Optimized status: %d\n",
                bytes_read, naive_status, opt_status);
        return 1;
    }

    /* Check 2: When both parsers return OK, all field values must match */
    if (naive_status == NAIVE_PARSE_OK) {
        if (naive_header.src_port != opt_header.src_port) {
            fprintf(stderr,
                    "Differential mismatch: src_port differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.src_port,
                    (unsigned int)opt_header.src_port);
            return 1;
        }

        if (naive_header.dst_port != opt_header.dst_port) {
            fprintf(stderr,
                    "Differential mismatch: dst_port differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.dst_port,
                    (unsigned int)opt_header.dst_port);
            return 1;
        }

        if (naive_header.length != opt_header.length) {
            fprintf(stderr,
                    "Differential mismatch: length differs (naive=%u, opt=%u)\n",
                    (unsigned int)naive_header.length,
                    (unsigned int)opt_header.length);
            return 1;
        }

        if (naive_header.checksum != opt_header.checksum) {
            fprintf(stderr,
                    "Differential mismatch: checksum differs (naive=0x%04X, opt=0x%04X)\n",
                    (unsigned int)naive_header.checksum,
                    (unsigned int)opt_header.checksum);
            return 1;
        }

        if (naive_header.payload_len != opt_header.payload_len) {
            fprintf(stderr,
                    "Differential mismatch: payload_len differs (naive=%zu, opt=%zu)\n",
                    naive_header.payload_len,
                    opt_header.payload_len);
            return 1;
        }

        if (naive_header.payload_len > 0) {
            if (memcmp(naive_header.payload, opt_header.payload, naive_header.payload_len) != 0) {
                fprintf(stderr, "Differential mismatch: payload content differs!\n");
                return 1;
            }
        }
    }

    return 0;
}
