# test_compiler.py — Integration tests for the full compile pipeline.
#
# Run with:  pytest tests/test_compiler.py -v

import pytest
from safeparse.compiler import compile_spec


def test_successful_compilation():
    """A valid spec should compile successfully."""
    result = compile_spec("format Foo { x: u8 y: u16 }", "naive")
    assert result["success"] is True
    assert result["c_code"] != ""
    assert result["format_name"] == "Foo"
    assert result["errors"] == []


def test_compilation_returns_errors_for_bad_type():
    """An invalid spec should return errors and no code."""
    result = compile_spec("format Foo { x: u64 }")
    assert result["success"] is False
    assert len(result["errors"]) > 0
    assert result["c_code"] == ""


def test_syntax_error_reported():
    """Unparseable input should return an error."""
    result = compile_spec("this is not valid syntax at all")
    assert result["success"] is False
    assert len(result["errors"]) > 0


def test_lexer_error_reported():
    """Input with invalid characters should return an error."""
    result = compile_spec("format Foo { x: u8; }")
    assert result["success"] is False
    assert len(result["errors"]) > 0


def test_both_modes_produce_output():
    """Both naive and optimized should produce valid (different) C code."""
    source = "format Foo { a: u16 b: u32 }"
    naive_result = compile_spec(source, "naive")
    opt_result = compile_spec(source, "optimized")
    assert naive_result["success"]
    assert opt_result["success"]
    # The code should differ because optimized merges bounds checks.
    assert naive_result["c_code"] != opt_result["c_code"]


def test_both_modes_same_struct():
    """Both modes should produce identical struct definitions."""
    source = "format Foo { a: u16 b: u32 c: u8 }"
    naive_code = compile_spec(source, "naive")["c_code"]
    opt_code = compile_spec(source, "optimized")["c_code"]
    # Both should contain the same struct fields.
    assert "uint16_t a;" in naive_code
    assert "uint16_t a;" in opt_code
    assert "uint32_t b;" in naive_code
    assert "uint32_t b;" in opt_code
    assert "uint8_t c;" in naive_code
    assert "uint8_t c;" in opt_code


def test_udp_header_both_modes():
    """The UDP header should compile in both modes."""
    source = """format UdpHeader {
        src_port:  u16
        dst_port:  u16
        length:    u16
        checksum:  u16
        payload:   bytes[length - 8]
    }"""
    naive_result = compile_spec(source, "naive")
    opt_result = compile_spec(source, "optimized")
    assert naive_result["success"]
    assert opt_result["success"]
    assert naive_result["format_name"] == "UdpHeader"


def test_png_ihdr_all_fixed():
    """The PNG IHDR spec (all fixed-size) should compile in both modes."""
    source = """format PngIhdr {
        width:              u32
        height:             u32
        bit_depth:          u8
        color_type:         u8
        compression_method: u8
        filter_method:      u8
        interlace_method:   u8
    }"""
    naive_result = compile_spec(source, "naive")
    opt_result = compile_spec(source, "optimized")
    assert naive_result["success"]
    assert opt_result["success"]
    # Optimized should have fewer PARSE_ERR_TOO_SHORT (1 group vs 7)
    naive_checks = naive_result["c_code"].count("PARSE_ERR_TOO_SHORT")
    opt_checks = opt_result["c_code"].count("PARSE_ERR_TOO_SHORT")
    assert opt_checks < naive_checks


def test_default_mode_is_naive():
    """Calling compile_spec without a mode should default to naive."""
    result = compile_spec("format Foo { x: u8 }")
    assert result["success"]
    # Naive mode for a single u8 field should have 2 TOO_SHORT checks.
    assert result["c_code"].count("PARSE_ERR_TOO_SHORT") == 2


def test_empty_spec_text():
    """An empty spec should return an error (not crash)."""
    result = compile_spec("")
    assert result["success"] is False
    assert len(result["errors"]) > 0
