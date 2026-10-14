# test_optimizer.py — Tests for the optimizer (field grouping).
#
# Run with:  pytest tests/test_optimizer.py -v

import pytest
from safeparse.lexer import tokenize
from safeparse.parser import parse_tokens
from safeparse.optimizer import make_field_groups


def _get_groups(source, mode):
    """Helper: parse a spec and return field groups for the given mode."""
    tokens = tokenize(source)
    ast = parse_tokens(tokens)
    return make_field_groups(ast.fields, mode)


def test_naive_one_group_per_field():
    """In naive mode, each field should be in its own group."""
    groups = _get_groups("format Foo { a: u16 b: u16 c: u32 }", "naive")
    assert len(groups) == 3
    assert groups[0].total_size == 2
    assert groups[1].total_size == 2
    assert groups[2].total_size == 4
    # Each group should have exactly one field.
    assert len(groups[0].fields) == 1
    assert len(groups[1].fields) == 1
    assert len(groups[2].fields) == 1


def test_optimized_merges_all_fixed():
    """Optimized mode should merge all fixed-size fields into one group."""
    groups = _get_groups("format Foo { a: u16 b: u16 c: u32 }", "optimized")
    assert len(groups) == 1
    assert groups[0].total_size == 8  # 2 + 2 + 4
    assert len(groups[0].fields) == 3
    assert groups[0].is_fixed


def test_optimized_splits_at_bytes():
    """A bytes[] field should break the current fixed-size group."""
    source = "format Foo { a: u16 b: u16 len: u16 data: bytes[len] c: u32 }"
    groups = _get_groups(source, "optimized")
    assert len(groups) == 3
    # Group 1: a, b, len (6 bytes)
    assert groups[0].is_fixed
    assert groups[0].total_size == 6
    assert len(groups[0].fields) == 3
    # Group 2: data (variable)
    assert not groups[1].is_fixed
    assert len(groups[1].fields) == 1
    # Group 3: c (4 bytes)
    assert groups[2].is_fixed
    assert groups[2].total_size == 4


def test_naive_handles_bytes():
    """Naive mode should handle bytes[] fields correctly."""
    source = "format Foo { length: u16 data: bytes[length] }"
    groups = _get_groups(source, "naive")
    assert len(groups) == 2
    assert groups[0].is_fixed
    assert groups[0].total_size == 2
    assert not groups[1].is_fixed


def test_optimized_single_field():
    """A single field should still work in optimized mode."""
    groups = _get_groups("format Foo { x: u8 }", "optimized")
    assert len(groups) == 1
    assert groups[0].total_size == 1
    assert groups[0].is_fixed


def test_invalid_mode_raises_error():
    """An invalid mode string should raise ValueError."""
    with pytest.raises(ValueError):
        _get_groups("format Foo { x: u8 }", "unknown_mode")


def test_optimized_all_bytes():
    """Multiple bytes[] fields should each be their own group."""
    source = "format Foo { a: u8 b: bytes[a] c: u8 d: bytes[c] }"
    groups = _get_groups(source, "optimized")
    assert len(groups) == 4
    assert groups[0].is_fixed      # a
    assert not groups[1].is_fixed   # b (bytes)
    assert groups[2].is_fixed      # c
    assert not groups[3].is_fixed   # d (bytes)
