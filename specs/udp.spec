# UDP Header — 8 bytes of fixed header followed by variable-length payload.
# The payload length is computed from the "length" field (total datagram
# length including the header, so payload = length - 8).

format UdpHeader {
    src_port:  u16
    dst_port:  u16
    length:    u16
    checksum:  u16
    payload:   bytes[length - 8]
}
