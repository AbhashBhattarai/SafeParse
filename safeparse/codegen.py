# codegen.py — Generates C source code from a checked FormatDef AST.
#
# Produces a complete C source file containing:
#   1. Necessary #include directives
#   2. Return-code #defines  (PARSE_OK, PARSE_ERR_TOO_SHORT, …)
#   3. A struct typedef for the format
#   4. A parse function that reads binary data into the struct
#
# Supports two modes:
#   "naive"     — one bounds check before EVERY field read
#   "optimized" — consecutive fixed-size fields share ONE bounds check

from safeparse.parser import IntegerType, BytesType
from safeparse.parser import NumberExpr, FieldRefExpr, BinaryExpr
from safeparse.optimizer import make_field_groups


# ---------------------------------------------------------------------------
# Type information table
# ---------------------------------------------------------------------------
# Maps spec type name → (C type name, byte size, endianness).

TYPE_INFO = {
    "u8":    ("uint8_t",  1, "big"),
    "u16":   ("uint16_t", 2, "big"),
    "u32":   ("uint32_t", 4, "big"),
    "u16le": ("uint16_t", 2, "little"),
    "u32le": ("uint32_t", 4, "little"),
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_c_code(format_def, mode):
    """
    Generate a complete C source file for a binary-format parser.

    WHAT: Produces the full .c file as a single string.
    WHY:  This is the main output of the SafeParse compiler.

    Parameters:
        format_def — a FormatDef AST node (already checked)
        mode       — "naive" or "optimized"

    Returns the C source code as a string.
    """
    lines = []
    lines.extend(_generate_includes())
    lines.append("")
    lines.extend(_generate_return_codes())
    lines.append("")
    lines.extend(_generate_struct(format_def))
    lines.append("")
    lines.extend(_generate_parse_function(format_def, mode))
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------

def _generate_includes():
    """
    Generate #include lines for the C standard-library types we need.

    WHAT: Produces two includes — stdint.h for uint8_t etc., stddef.h for size_t.
    WHY:  The generated parser uses exact-width integer types and size_t.
    """
    return [
        "#include <stdint.h>",
        "#include <stddef.h>",
    ]


def _generate_return_codes():
    """
    Generate #define constants for the parse function's return codes.

    WHAT: Three codes — OK, TOO_SHORT (not enough data), BAD_LENGTH
          (a computed length was negative or nonsensical).
    WHY:  The caller of the parse function checks the return code to
          know whether parsing succeeded.
    """
    return [
        "/* Return codes for the parse function */",
        "#define PARSE_OK             0",
        "#define PARSE_ERR_TOO_SHORT  1",
        "#define PARSE_ERR_BAD_LENGTH 2",
    ]


def _generate_struct(format_def):
    """
    Generate the C struct typedef for the format.

    WHAT: Creates a struct with one member per field.  Integer fields
          become uint*_t members; bytes[] fields become a pointer plus
          a length member.
    WHY:  The parse function fills in this struct from raw bytes.
    """
    lines = []
    lines.append("/* Parsed representation of {} */".format(format_def.name))
    lines.append("typedef struct {")

    for field in format_def.fields:
        if isinstance(field.field_type, IntegerType):
            c_type = TYPE_INFO[field.field_type.type_name][0]
            lines.append("    {} {};".format(c_type, field.name))
        elif isinstance(field.field_type, BytesType):
            # A bytes[] field becomes a pointer to the data inside the
            # buffer and a length value.
            lines.append("    const uint8_t *{};".format(field.name))
            lines.append("    size_t {}_len;".format(field.name))

    lines.append("}} {};".format(format_def.name))
    return lines


def _generate_parse_function(format_def, mode):
    """
    Generate the parse function that reads bytes into the struct.

    WHAT: Produces the function signature, offset tracking, bounds
          checks, field reads, and the return statement.
    WHY:  This is where the safety happens — every read is guarded
          by a bounds check to prevent out-of-bounds memory access.
    """
    lines = []
    func_name = "parse_{}".format(format_def.name)
    struct_name = format_def.name

    lines.append("/* Parse raw bytes into a {} struct */".format(struct_name))
    lines.append(
        "int {}(const uint8_t *buf, size_t len, {} *out) {{".format(
            func_name, struct_name
        )
    )
    lines.append("    size_t offset = 0;")

    # Use the optimizer to group fields based on the mode.
    groups = make_field_groups(format_def.fields, mode)

    for group in groups:
        lines.append("")
        lines.extend(_generate_group_code(group))

    lines.append("")
    lines.append("    return PARSE_OK;")
    lines.append("}")
    return lines


# ---------------------------------------------------------------------------
# Group-level code generation
# ---------------------------------------------------------------------------

def _generate_group_code(group):
    """
    Generate C code for one group of fields (one bounds check).

    WHAT: Emits the bounds check and field-reading code for one group.
    WHY:  In naive mode each group has one field.  In optimized mode,
          consecutive fixed-size fields are merged into one group with
          a single bounds check, reducing overhead.
    """
    lines = []

    if group.is_fixed:
        # --- Fixed-size group: one bounds check for the total size -----------
        field_names = ", ".join(f.name for f in group.fields)
        lines.append(
            "    /* Bounds check for: {} ({} bytes) */".format(
                field_names, group.total_size
            )
        )
        # The check is written in two steps to avoid unsigned overflow:
        # 1. Make sure offset <= len  (so len - offset doesn't wrap)
        # 2. Make sure len - offset >= needed
        lines.append("    if (offset > len) return PARSE_ERR_TOO_SHORT;")
        lines.append(
            "    if (len - offset < {}) return PARSE_ERR_TOO_SHORT;".format(
                group.total_size
            )
        )

        # Now read each field in the group — no individual checks needed.
        for field in group.fields:
            lines.extend(_generate_field_read(field))
    else:
        # --- Variable-size group: a single bytes[] field ---------------------
        field = group.fields[0]
        lines.extend(_generate_bytes_field_code(field))

    return lines


# ---------------------------------------------------------------------------
# Field-level code generation
# ---------------------------------------------------------------------------

def _generate_field_read(field):
    """
    Generate C code to read one fixed-size integer field from the buffer.

    WHAT: Reads 1, 2, or 4 bytes from buf[offset], assembles them in
          the correct byte order, stores the result in the struct, and
          advances offset.
    WHY:  Different integer sizes and endiannesses need different code.
          Big-endian reads the high byte first; little-endian reads
          the low byte first.
    """
    lines = []
    type_name = field.field_type.type_name
    c_type, byte_size, endianness = TYPE_INFO[type_name]
    name = field.name

    lines.append("    /* Read field: {} ({}) */".format(name, type_name))

    if byte_size == 1:
        # u8: just one byte, no byte-order issue.
        lines.append("    out->{} = buf[offset];".format(name))

    elif byte_size == 2 and endianness == "big":
        # u16 big-endian: high byte at offset, low byte at offset+1.
        lines.append(
            "    out->{name} = (uint16_t)"
            "(((uint16_t)buf[offset] << 8) | buf[offset + 1]);".format(
                name=name
            )
        )

    elif byte_size == 2 and endianness == "little":
        # u16le little-endian: low byte at offset, high byte at offset+1.
        lines.append(
            "    out->{name} = (uint16_t)"
            "(((uint16_t)buf[offset + 1] << 8) | buf[offset]);".format(
                name=name
            )
        )

    elif byte_size == 4 and endianness == "big":
        # u32 big-endian: most significant byte first.
        lines.append(
            "    out->{name} = "
            "((uint32_t)buf[offset] << 24)"
            " | ((uint32_t)buf[offset + 1] << 16)"
            " | ((uint32_t)buf[offset + 2] << 8)"
            " | (uint32_t)buf[offset + 3];".format(name=name)
        )

    elif byte_size == 4 and endianness == "little":
        # u32le little-endian: least significant byte first.
        lines.append(
            "    out->{name} = "
            "((uint32_t)buf[offset + 3] << 24)"
            " | ((uint32_t)buf[offset + 2] << 16)"
            " | ((uint32_t)buf[offset + 1] << 8)"
            " | (uint32_t)buf[offset];".format(name=name)
        )

    lines.append("    offset += {};".format(byte_size))
    return lines


def _generate_bytes_field_code(field):
    """
    Generate C code for a variable-length bytes[EXPR] field.

    WHAT: Computes the dynamic length, validates it against underflow,
          performs a bounds check, and stores a pointer + length in
          the struct.
    WHY:  bytes[] fields have a runtime-dependent size.  We must guard
          against three dangers:
          1. The computed length could underflow (e.g. length - 8 when
             length < 8), which would wrap to a huge size_t value.
          2. The buffer might not have enough bytes left.
          3. The offset might already be past the end of the buffer.
    """
    lines = []
    name = field.name
    size_expr = field.field_type.size_expr

    lines.append("    /* Read variable-length field: {} */".format(name))
    lines.append("    {")

    # Generate the underflow guard (if the expression involves subtraction).
    underflow_check = _generate_underflow_check(size_expr)
    if underflow_check is not None:
        lines.append("        " + underflow_check)

    # Compute the byte length.
    length_expr_c = _expr_to_c(size_expr)
    lines.append(
        "        size_t {name}_len = (size_t)({expr});".format(
            name=name, expr=length_expr_c
        )
    )

    # Bounds check: is there enough data left in the buffer?
    lines.append("        if (offset > len) return PARSE_ERR_TOO_SHORT;")
    lines.append(
        "        if (len - offset < {name}_len)"
        " return PARSE_ERR_TOO_SHORT;".format(name=name)
    )

    # Store the pointer and length in the struct.
    lines.append("        out->{} = buf + offset;".format(name))
    lines.append(
        "        out->{name}_len = {name}_len;".format(name=name)
    )
    lines.append("        offset += {}_len;".format(name))
    lines.append("    }")
    return lines


# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------

def _expr_to_c(expr):
    """
    Convert a size-expression AST node to a C expression string.

    WHAT: Turns NumberExpr / FieldRefExpr / BinaryExpr into C code.
    WHY:  The code generator needs C syntax for the bytes[] length
          calculation.
    """
    if isinstance(expr, NumberExpr):
        return str(expr.value)

    if isinstance(expr, FieldRefExpr):
        # Refer to the field via the output struct pointer.
        return "out->{}".format(expr.field_name)

    if isinstance(expr, BinaryExpr):
        left_c = _expr_to_c(expr.left)
        right_c = _expr_to_c(expr.right)
        return "({} {} {})".format(left_c, expr.operator, right_c)

    # Should never reach here if the checker did its job.
    return "0"


def _generate_underflow_check(expr):
    """
    Generate a C guard against unsigned underflow in a size expression.

    WHAT: If the expression involves subtraction (e.g. length - 8),
          emit an if-statement that returns PARSE_ERR_BAD_LENGTH when
          the subtraction would produce a negative (wrapped) result.
    WHY:  Unsigned integers in C wrap around on underflow.  For example,
          if length = 3 and we compute (length - 8), the uint16_t result
          is 65531, which would cause an enormous out-of-bounds read.

    Returns a C statement string, or None if no guard is needed.
    """
    conditions = _collect_underflow_conditions(expr)
    if not conditions:
        return None

    combined = " && ".join(conditions)
    return "if (!({cond})) return PARSE_ERR_BAD_LENGTH;".format(
        cond=combined
    )


def _collect_underflow_conditions(expr):
    """
    Walk the expression tree and collect conditions that prevent underflow.

    WHAT: For every subtraction A - B in the tree, adds the condition
          "A >= B" (meaning the subtraction is safe).
    WHY:  Each subtraction can independently underflow, so we need a
          guard for each one.
    """
    conditions = []

    if isinstance(expr, NumberExpr):
        return conditions

    if isinstance(expr, FieldRefExpr):
        return conditions

    if isinstance(expr, BinaryExpr):
        if expr.operator == "-":
            left_c = _expr_to_c(expr.left)
            right_c = _expr_to_c(expr.right)
            conditions.append("{} >= {}".format(left_c, right_c))

        # Recurse into sub-expressions.
        conditions.extend(_collect_underflow_conditions(expr.left))
        conditions.extend(_collect_underflow_conditions(expr.right))

    return conditions
