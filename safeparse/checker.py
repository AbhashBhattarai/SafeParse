# checker.py — Semantic checker for the parsed AST.
#
# The parser only checks SYNTAX (correct token order).  The checker
# looks at MEANING: are field names unique?  Are types valid?  Do
# bytes[] expressions refer to fields that actually exist and that
# come before this field?
#
# Returns a list of error-message strings.  An empty list means the
# spec is valid.

from safeparse.parser import IntegerType, BytesType
from safeparse.parser import NumberExpr, FieldRefExpr, BinaryExpr


# The set of built-in integer type names that we recognise.
VALID_INTEGER_TYPES = {"u8", "u16", "u32", "u16le", "u32le"}


def check_format(format_def):
    """
    Check a FormatDef AST node for semantic errors.

    WHAT: Walks through every field and checks for five kinds of error:
      1. Duplicate field name
      2. Unknown type name
      3. bytes[] expression that refers to a field defined LATER
         (forward reference)
      4. bytes[] expression that refers to a field that does not exist
      5. bytes[] expression that refers to a non-integer field

    WHY: Catching these errors here gives the user clear messages with
    line numbers, instead of silently generating broken C code.

    Returns a list of error strings (empty if no errors).
    """
    errors = []

    # Track which field names we have seen so far, in order.
    # Maps field name -> line number where it was first defined.
    seen_field_names = {}

    for field in format_def.fields:
        # --- Check 1: duplicate field name -----------------------------------
        if field.name in seen_field_names:
            errors.append(
                "Line {}: duplicate field name '{}' "
                "(first defined on line {})".format(
                    field.line_number,
                    field.name,
                    seen_field_names[field.name],
                )
            )
        else:
            # Only add the name the first time we see it.
            seen_field_names[field.name] = field.line_number

        # --- Check 2: unknown integer type -----------------------------------
        if isinstance(field.field_type, IntegerType):
            if field.field_type.type_name not in VALID_INTEGER_TYPES:
                errors.append(
                    "Line {}: unknown type '{}'".format(
                        field.line_number, field.field_type.type_name
                    )
                )

        # --- Checks 3–5: validate bytes[] size expressions -------------------
        if isinstance(field.field_type, BytesType):
            _check_size_expr(
                field.field_type.size_expr,
                field.name,
                field.line_number,
                seen_field_names,
                format_def.fields,
                errors,
            )

    return errors


def _check_size_expr(expr, current_field_name, line_number,
                     seen_field_names, all_fields, errors):
    """
    Recursively check a size expression inside bytes[EXPR].

    WHAT: Validates every field reference inside the expression tree.
    WHY:  A bytes[] size like 'length - 8' needs 'length' to be:
          - a real field name (not misspelled)
          - defined BEFORE this field (not a forward reference)
          - an integer type (not another bytes[] field)

    Appends any error messages to the *errors* list.
    """
    if isinstance(expr, NumberExpr):
        # A literal number is always valid — nothing to check.
        return

    if isinstance(expr, FieldRefExpr):
        referred_name = expr.field_name

        # --- Does this field exist at all? -----------------------------------
        referred_field = None
        for field in all_fields:
            if field.name == referred_name:
                referred_field = field
                break

        if referred_field is None:
            errors.append(
                "Line {}: bytes[] size refers to unknown field '{}'".format(
                    expr.line_number, referred_name
                )
            )
            return

        # --- Is it a self-reference? -----------------------------------------
        if referred_name == current_field_name:
            errors.append(
                "Line {}: bytes[] size refers to itself ('{}')".format(
                    line_number, referred_name
                )
            )
            return

        # --- Is it defined before the current field? -------------------------
        # We check seen_field_names, which only contains fields we have
        # already fully processed.  The current field IS in seen_field_names
        # (added by the caller), so we also need the self-reference check
        # above to catch that case.
        if referred_name not in seen_field_names:
            errors.append(
                "Line {}: bytes[] size refers to field '{}' which is "
                "defined later (forward reference)".format(
                    line_number, referred_name
                )
            )
            return

        # --- Is the referred field an integer type? --------------------------
        if isinstance(referred_field.field_type, BytesType):
            errors.append(
                "Line {}: bytes[] size refers to field '{}' which is "
                "not an integer type".format(
                    line_number, referred_name
                )
            )
            return

        return

    if isinstance(expr, BinaryExpr):
        # Recursively check both sides of a + or - expression.
        _check_size_expr(
            expr.left, current_field_name, line_number,
            seen_field_names, all_fields, errors,
        )
        _check_size_expr(
            expr.right, current_field_name, line_number,
            seen_field_names, all_fields, errors,
        )
        return
