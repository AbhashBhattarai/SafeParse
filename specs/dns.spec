# DNS Header — The fixed 12-byte header at the start of every DNS message.
# All fields are big-endian u16 values.
# This is another good test for the optimizer (6 fields, 12 bytes,
# all mergeable into one bounds check).

format DnsHeader {
    id:       u16
    flags:    u16
    qdcount:  u16
    ancount:  u16
    nscount:  u16
    arcount:  u16
}
