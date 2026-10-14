# test_lexer.py — Tests for the lexer module.
#
# Each test function checks one aspect of the tokenizer.
# Run with:  pytest tests/test_lexer.py -v

import pytest
from safeparse.lexer import (
    tokenize, Token,
    FORMAT, IDENT, LBRACE, RBRACE, COLON,
    LBRACKET, RBRACKET, PLUS, MINUS, NUMBER, EOF,
)


def test_simple_format():
    """Tokenize a minimal format definition and check every token."""
    source = "format Foo { x: u8 }"
    tokens = tokenize(source)
    assert tokens[0] == Token(FORMAT, "format", 1)
    assert tokens[1] == Token(IDENT, "Foo", 1)
    assert tokens[2] == Token(LBRACE, "{", 1)
    assert tokens[3] == Token(IDENT, "x", 1)
    assert tokens[4] == Token(COLON, ":", 1)
    assert tokens[5] == Token(IDENT, "u8", 1)
    assert tokens[6] == Token(RBRACE, "}", 1)
    assert tokens[7] == Token(EOF, "", 1)


def test_multiline_line_numbers():
    """Line numbers should be tracked correctly across newlines."""
    source = "format Foo {\n    x: u8\n    y: u16\n}"
    tokens = tokenize(source)
    # "format" is on line 1
    assert tokens[0].line_number == 1
    # "x" is on line 2
    x_token = tokens[3]
    assert x_token.value == "x"
    assert x_token.line_number == 2
    # "y" is on line 3
    y_token = tokens[7]
    assert y_token.value == "y"
    assert y_token.line_number == 3


def test_bytes_with_expression():
    """The tokens for bytes[length - 8] should be correct."""
    source = "bytes[length - 8]"
    tokens = tokenize(source)
    assert tokens[0] == Token(IDENT, "bytes", 1)
    assert tokens[1] == Token(LBRACKET, "[", 1)
    assert tokens[2] == Token(IDENT, "length", 1)
    assert tokens[3] == Token(MINUS, "-", 1)
    assert tokens[4] == Token(NUMBER, "8", 1)
    assert tokens[5] == Token(RBRACKET, "]", 1)


def test_comments_are_skipped():
    """Lines starting with # should be ignored."""
    source = "# this is a comment\nformat Foo { }"
    tokens = tokenize(source)
    # The first real token should be FORMAT on line 2.
    assert tokens[0] == Token(FORMAT, "format", 2)


def test_unknown_character_raises_error():
    """An unexpected character like ; should raise SyntaxError."""
    with pytest.raises(SyntaxError):
        tokenize("format Foo { x: u8; }")


def test_number_tokens():
    """Multi-digit numbers should be tokenized as a single NUMBER."""
    source = "123 456"
    tokens = tokenize(source)
    assert tokens[0] == Token(NUMBER, "123", 1)
    assert tokens[1] == Token(NUMBER, "456", 1)


def test_plus_token():
    """The + character should become a PLUS token."""
    source = "a + b"
    tokens = tokenize(source)
    assert tokens[0] == Token(IDENT, "a", 1)
    assert tokens[1] == Token(PLUS, "+", 1)
    assert tokens[2] == Token(IDENT, "b", 1)


def test_empty_input():
    """Empty input should produce just an EOF token."""
    tokens = tokenize("")
    assert len(tokens) == 1
    assert tokens[0].token_type == EOF


def test_underscore_in_identifiers():
    """Identifiers can contain underscores."""
    tokens = tokenize("my_field _private")
    assert tokens[0].value == "my_field"
    assert tokens[1].value == "_private"


def test_inline_comment():
    """A comment in the middle of a line should stop at the newline."""
    source = "format Foo { # comment\n x: u8 }"
    tokens = tokenize(source)
    # After FORMAT, IDENT(Foo), LBRACE, the comment is skipped.
    # Next real token is IDENT(x) on line 2.
    assert tokens[3] == Token(IDENT, "x", 2)
