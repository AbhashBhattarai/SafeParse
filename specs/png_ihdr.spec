# PNG IHDR chunk — The first chunk in every PNG file.
# All fields are fixed-size (13 bytes total), all big-endian.
# This is a good test case for the optimizer because all fields
# can be merged into a single bounds check.

format PngIhdr {
    width:              u32
    height:             u32
    bit_depth:          u8
    color_type:         u8
    compression_method: u8
    filter_method:      u8
    interlace_method:   u8
}
