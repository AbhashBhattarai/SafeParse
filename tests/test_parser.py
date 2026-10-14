# test_parser.py — Tests for the recursive-descent parser.
#
# Run with:  pytest tests/test_parser.py -v

import pytest
from safeparse.lexer import tokenize
from safeparse.parser import (
    parse_tokens, ParseError,
    FormatDef, Field, IntegerType, BytesType,
    NumberExpr, FieldRefExpr, BinaryExpr,
)


def test_simple_format():
    """Parse a format with one integer field."""
    tokens = tokenize("format Foo { x: u8 }")
    ast = parse_tokens(tokens)
    assert isinstance(ast, FormatDef)
    assert ast.name == "Foo"
    assert len(ast.fields) == 1
    assert ast.fields[0].name == "x"
    assert isinstance(ast.fields[0].field_type, IntegerType)
    assert ast.fields[0].field_type.type_name == "u8"


def test_multiple_fields():
    """Parse a format with several fields."""
    source = "format Bar { a: u16 b: u32 c: u8 }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    assert len(ast.fields) == 3
    assert ast.fields[0].name == "a"
    assert ast.fields[0].field_type.type_name == "u16"
    assert ast.fields[1].name == "b"
    assert ast.fields[1].field_type.type_name == "u32"
    assert ast.fields[2].name == "c"
    assert ast.fields[2].field_type.type_name == "u8"


def test_bytes_fixed_size():
    """Parse bytes[10] — a fixed-size byte array."""
    source = "format Baz { data: bytes[10] }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    field = ast.fields[0]
    assert field.name == "data"
    assert isinstance(field.field_type, BytesType)
    assert isinstance(field.field_type.size_expr, NumberExpr)
    assert field.field_type.size_expr.value == 10


def test_bytes_field_reference():
    """Parse bytes[length] — size depends on another field."""
    source = "format Baz { length: u16 data: bytes[length] }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    field = ast.fields[1]
    assert isinstance(field.field_type, BytesType)
    assert isinstance(field.field_type.size_expr, FieldRefExpr)
    assert field.field_type.size_expr.field_name == "length"


def test_bytes_binary_expression():
    """Parse bytes[length - 8] — an arithmetic expression."""
    source = "format Baz { length: u16 data: bytes[length - 8] }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    field = ast.fields[1]
    assert isinstance(field.field_type, BytesType)
    expr = field.field_type.size_expr
    assert isinstance(expr, BinaryExpr)
    assert expr.operator == "-"
    assert isinstance(expr.left, FieldRefExpr)
    assert expr.left.field_name == "length"
    assert isinstance(expr.right, NumberExpr)
    assert expr.right.value == 8


def test_bytes_addition_expression():
    """Parse bytes[a + b] — addition in size expression."""
    source = "format Baz { a: u8 b: u8 data: bytes[a + b] }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    expr = ast.fields[2].field_type.size_expr
    assert isinstance(expr, BinaryExpr)
    assert expr.operator == "+"


def test_parse_error_missing_brace():
    """A missing closing brace should raise ParseError."""
    tokens = tokenize("format Foo { x: u8")
    with pytest.raises(ParseError):
        parse_tokens(tokens)


def test_parse_error_missing_colon():
    """A missing colon between field name and type should raise ParseError."""
    tokens = tokenize("format Foo { x u8 }")
    with pytest.raises(ParseError):
        parse_tokens(tokens)


def test_parse_error_missing_format_keyword():
    """Input without the format keyword should raise ParseError."""
    tokens = tokenize("Foo { x: u8 }")
    with pytest.raises(ParseError):
        parse_tokens(tokens)


def test_little_endian_types():
    """u16le and u32le should be parsed as IntegerType."""
    source = "format LE { a: u16le b: u32le }"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    assert ast.fields[0].field_type.type_name == "u16le"
    assert ast.fields[1].field_type.type_name == "u32le"


def test_field_line_numbers():
    """Each field should record the correct source line number."""
    source = "format Foo {\n    x: u8\n    y: u16\n}"
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    assert ast.fields[0].line_number == 2
    assert ast.fields[1].line_number == 3


def test_udp_header_spec():
    """The full UDP header spec should parse correctly."""
    source = """format UdpHeader {
        src_port:  u16
        dst_port:  u16
        length:    u16
        checksum:  u16
        payload:   bytes[length - 8]
    }"""
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    assert ast.name == "UdpHeader"
    assert len(ast.fields) == 5
    assert ast.fields[4].name == "payload"
    assert isinstance(ast.fields[4].field_type, BytesType)
