# create_corpus.py — Generate binary seed corpus files for SafeParse fuzz testing.
#
# WHAT: Generates valid binary seed inputs for UDP, PNG IHDR, and DNS parsers
#       using Python's struct module, and saves them to c_tests/corpus/ subdirectories.
#
# WHY:  Fuzzers like libFuzzer and AFL++ explore code paths much faster when seeded
#       with valid initial inputs (the "corpus"). Starting from valid packets lets
#       fuzzers discover edge cases near the boundary of valid and invalid formats.
#
# USAGE:
#   python c_tests/create_corpus.py

import os
import struct


def write_file(target_path, data):
    """
    Write binary data to a file on disk, creating directories as needed.

    WHAT: Ensures the parent directory exists and writes raw bytes to target_path.
    WHY:  Seed corpus files are binary (.bin) files stored in protocol-specific
          subdirectories.
    """
    directory = os.path.dirname(target_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    file_handle = open(target_path, "wb")
    file_handle.write(data)
    file_handle.close()


def generate_valid_udp():
    """
    Build a valid 20-byte UDP packet (8-byte header + 12-byte payload).

    WHAT: Packs source port (12345), destination port (80), length (20),
          checksum (0), followed by 12 bytes of ASCII payload data.
    WHY:  The SafeParse UDP specification defines payload as bytes[length - 8].
          A 20-byte packet with length=20 satisfies both the 8-byte fixed header
          and the 12-byte variable-length payload requirement.
    """
    src_port = 12345
    dst_port = 80
    length = 20
    checksum = 0

    header_bytes = struct.pack(">HHHH", src_port, dst_port, length, checksum)
    payload_bytes = b"Hello, Safe!"
    packet_bytes = header_bytes + payload_bytes
    return packet_bytes


def generate_min_udp():
    """
    Build a minimal valid 8-byte UDP packet with no payload.

    WHAT: Packs source port (53), destination port (53), length (8), checksum (0)
          with 0 bytes of payload.
    WHY:  The minimum valid UDP header has length=8 and an empty payload
          (length - 8 = 0). This tests the lower boundary condition for
          variable-length payload parsing.
    """
    src_port = 53
    dst_port = 53
    length = 8
    checksum = 0

    packet_bytes = struct.pack(">HHHH", src_port, dst_port, length, checksum)
    return packet_bytes


def generate_valid_png_ihdr():
    """
    Build a valid 13-byte PNG IHDR chunk data payload.

    WHAT: Packs width (800), height (600), bit_depth (8), color_type (6),
          compression_method (0), filter_method (0), and interlace_method (0).
    WHY:  specs/png_ihdr.spec specifies exactly 13 fixed-size big-endian fields.
          This provides a valid seed matching the chunk structure of standard PNG images.
    """
    width = 800
    height = 600
    bit_depth = 8
    color_type = 6
    compression_method = 0
    filter_method = 0
    interlace_method = 0

    packet_bytes = struct.pack(
        ">IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        compression_method,
        filter_method,
        interlace_method,
    )
    return packet_bytes


def generate_valid_dns():
    """
    Build a valid 12-byte DNS header.

    WHAT: Packs transaction id (0x1234), flags (0x0100 for standard query),
          qdcount (1 question), ancount (0 answers), nscount (0 authority records),
          and arcount (0 additional records).
    WHY:  specs/dns.spec specifies 6 big-endian 16-bit integers totaling 12 bytes.
          This provides a valid seed representing a standard DNS query header.
    """
    trans_id = 0x1234
    flags = 0x0100
    qdcount = 1
    ancount = 0
    nscount = 0
    arcount = 0

    packet_bytes = struct.pack(
        ">HHHHHH",
        trans_id,
        flags,
        qdcount,
        ancount,
        nscount,
        arcount,
    )
    return packet_bytes


def main():
    """
    Main entry point for generating all seed corpus files.

    WHAT: Iterates through each protocol seed, generates the binary payload,
          writes it to disk under c_tests/corpus/, and prints confirmation.
    WHY:  Automates seed generation so developers and fuzzing scripts can easily
          populate or refresh the corpus with a single command.
    """
    # Locate project directory structure
    current_dir = os.path.dirname(os.path.abspath(__file__))
    corpus_root = os.path.join(current_dir, "corpus")

    seed_entries = [
        ("udp", "valid_udp.bin", generate_valid_udp(), 20),
        ("udp", "min_udp.bin", generate_min_udp(), 8),
        ("png_ihdr", "valid_ihdr.bin", generate_valid_png_ihdr(), 13),
        ("dns", "valid_dns.bin", generate_valid_dns(), 12),
    ]

    print("Generating SafeParse fuzzing seed corpus...")

    for entry in seed_entries:
        spec_name = entry[0]
        file_name = entry[1]
        data_bytes = entry[2]
        expected_size = entry[3]

        actual_size = len(data_bytes)
        if actual_size != expected_size:
            print("ERROR: {}/{} size mismatch! Expected {}, got {}".format(
                spec_name, file_name, expected_size, actual_size
            ))
            continue

        target_file = os.path.join(corpus_root, spec_name, file_name)
        write_file(target_file, data_bytes)
        print("  Created: {} ({} bytes)".format(target_file, actual_size))

    print("Corpus generation complete.")


if __name__ == "__main__":
    main()
