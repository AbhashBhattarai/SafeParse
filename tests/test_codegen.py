# test_codegen.py — Tests for the C code generator.
#
# Run with:  pytest tests/test_codegen.py -v

import pytest
from safeparse.compiler import compile_spec


def test_struct_definition():
    """The generated code should contain a correct struct typedef."""
    result = compile_spec("format Foo { x: u8 y: u16 }", "naive")
    assert result["success"]
    code = result["c_code"]
    assert "typedef struct" in code
    assert "uint8_t x;" in code
    assert "uint16_t y;" in code
    assert "} Foo;" in code


def test_parse_function_signature():
    """The parse function should have the correct name and parameters."""
    result = compile_spec("format Foo { x: u8 }", "naive")
    code = result["c_code"]
    assert "int parse_Foo(" in code
    assert "const uint8_t *buf" in code
    assert "size_t len" in code
    assert "Foo *out" in code


def test_return_codes_defined():
    """All three return-code #defines should be present."""
    result = compile_spec("format Foo { x: u8 }", "naive")
    code = result["c_code"]
    assert "#define PARSE_OK" in code
    assert "#define PARSE_ERR_TOO_SHORT" in code
    assert "#define PARSE_ERR_BAD_LENGTH" in code


def test_includes():
    """The generated code should include stdint.h and stddef.h."""
    result = compile_spec("format Foo { x: u8 }", "naive")
    code = result["c_code"]
    assert "#include <stdint.h>" in code
    assert "#include <stddef.h>" in code


def test_naive_individual_checks():
    """In naive mode, each field should have its own bounds check."""
    source = "format Foo { a: u16 b: u16 }"
    result = compile_spec(source, "naive")
    code = result["c_code"]
    # Each field gets 2 lines of bounds check, so 4 "return PARSE_ERR_TOO_SHORT".
    # We count "return PARSE_ERR_TOO_SHORT" to exclude the #define line.
    check_count = code.count("return PARSE_ERR_TOO_SHORT")
    assert check_count == 4


def test_optimized_merged_checks():
    """In optimized mode, consecutive fixed-size fields share one check."""
    source = "format Foo { a: u16 b: u16 }"
    result = compile_spec(source, "optimized")
    code = result["c_code"]
    # One merged check: 2 "return PARSE_ERR_TOO_SHORT" (excludes #define).
    check_count = code.count("return PARSE_ERR_TOO_SHORT")
    assert check_count == 2


def test_bytes_field_struct_members():
    """bytes[] fields should generate a pointer and a length member."""
    source = "format Foo { len: u16 data: bytes[len] }"
    result = compile_spec(source, "naive")
    code = result["c_code"]
    assert "const uint8_t *data;" in code
    assert "size_t data_len;" in code


def test_bytes_field_underflow_check():
    """bytes[field - N] should generate a BAD_LENGTH underflow check."""
    source = "format Foo { length: u16 data: bytes[length - 4] }"
    result = compile_spec(source, "naive")
    code = result["c_code"]
    assert "PARSE_ERR_BAD_LENGTH" in code
    # The check should compare length >= 4.
    assert "out->length >= 4" in code


def test_big_endian_u16():
    """u16 should read high byte first (big-endian)."""
    result = compile_spec("format Foo { x: u16 }", "naive")
    code = result["c_code"]
    assert "buf[offset] << 8" in code


def test_little_endian_u16():
    """u16le should read low byte first (little-endian)."""
    result = compile_spec("format Foo { x: u16le }", "naive")
    code = result["c_code"]
    assert "buf[offset + 1] << 8" in code


def test_big_endian_u32():
    """u32 should read four bytes in big-endian order."""
    result = compile_spec("format Foo { x: u32 }", "naive")
    code = result["c_code"]
    assert "buf[offset] << 24" in code


def test_little_endian_u32():
    """u32le should read four bytes in little-endian order."""
    result = compile_spec("format Foo { x: u32le }", "naive")
    code = result["c_code"]
    assert "buf[offset + 3] << 24" in code


def test_parse_ok_at_end():
    """The parse function should return PARSE_OK at the end."""
    result = compile_spec("format Foo { x: u8 }", "naive")
    code = result["c_code"]
    assert "return PARSE_OK;" in code


def test_offset_advances():
    """The offset should be incremented after each field read."""
    result = compile_spec("format Foo { a: u16 b: u32 }", "naive")
    code = result["c_code"]
    assert "offset += 2;" in code
    assert "offset += 4;" in code
