# test_checker.py — Tests for the semantic checker.
#
# Run with:  pytest tests/test_checker.py -v

import pytest
from safeparse.lexer import tokenize
from safeparse.parser import parse_tokens
from safeparse.checker import check_format


def _check(source):
    """Helper: tokenize, parse, and check a spec.  Returns error list."""
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    return check_format(ast)


def test_valid_format_no_errors():
    """A valid format with only integer fields should produce no errors."""
    errors = _check("format Foo { x: u8 y: u16 z: u32 }")
    assert errors == []


def test_valid_format_with_bytes():
    """A valid format with a bytes[] field should produce no errors."""
    errors = _check("format Foo { length: u16 data: bytes[length] }")
    assert errors == []


def test_valid_udp_header():
    """The full UDP header spec should have no errors."""
    source = """format UdpHeader {
        src_port:  u16
        dst_port:  u16
        length:    u16
        checksum:  u16
        payload:   bytes[length - 8]
    }"""
    errors = _check(source)
    assert errors == []


def test_duplicate_field_name():
    """Using the same field name twice should produce an error."""
    errors = _check("format Foo { x: u8 x: u16 }")
    assert len(errors) == 1
    assert "duplicate" in errors[0].lower()
    assert "'x'" in errors[0]


def test_unknown_type():
    """An unrecognised type name should produce an error."""
    errors = _check("format Foo { x: u64 }")
    assert len(errors) == 1
    assert "unknown type" in errors[0].lower()
    assert "'u64'" in errors[0]


def test_forward_reference():
    """Referring to a field defined later should produce an error."""
    errors = _check("format Foo { data: bytes[length] length: u16 }")
    assert len(errors) == 1
    error_lower = errors[0].lower()
    assert "forward" in error_lower or "later" in error_lower


def test_unknown_field_reference():
    """Referring to a field that does not exist should produce an error."""
    errors = _check("format Foo { data: bytes[bogus] }")
    assert len(errors) == 1
    assert "unknown field" in errors[0].lower()
    assert "'bogus'" in errors[0]


def test_non_integer_field_reference():
    """bytes[] size referring to another bytes[] field should error."""
    source = "format Foo { a: u16 b: bytes[a] c: bytes[b] }"
    errors = _check(source)
    assert len(errors) == 1
    assert "not an integer" in errors[0].lower()


def test_self_reference():
    """A bytes[] field referring to itself should produce an error."""
    errors = _check("format Foo { data: bytes[data] }")
    assert len(errors) == 1
    assert "itself" in errors[0].lower()


def test_multiple_errors_reported():
    """All errors should be reported, not just the first one."""
    source = "format Foo { x: u64 x: u8 }"
    errors = _check(source)
    # Should have both "unknown type" and "duplicate"
    assert len(errors) == 2


def test_valid_little_endian_types():
    """u16le and u32le should be accepted as valid types."""
    errors = _check("format Foo { a: u16le b: u32le }")
    assert errors == []


def test_bytes_with_subtraction():
    """bytes[field - constant] should be valid if field is defined before."""
    errors = _check("format Foo { len: u16 data: bytes[len - 4] }")
    assert errors == []
