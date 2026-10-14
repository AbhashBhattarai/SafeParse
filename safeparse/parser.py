# parser.py — Recursive-descent parser for the spec language.
#
# Reads a flat list of tokens (from the lexer) and builds an AST
# (Abstract Syntax Tree) made of simple Python objects.  The AST
# is what the rest of the compiler works with.
#
# Grammar (written in an informal BNF style):
#
#   format_def  = FORMAT IDENT LBRACE field* RBRACE
#   field       = IDENT COLON type_spec
#   type_spec   = "bytes" LBRACKET size_expr RBRACKET
#               | IDENT                                 (e.g. u16, u32le)
#   size_expr   = term ((PLUS | MINUS) term)*
#   term        = NUMBER | IDENT

from safeparse.lexer import (
    FORMAT, LBRACE, RBRACE, COLON, LBRACKET, RBRACKET,
    PLUS, MINUS, IDENT, NUMBER, EOF,
)


# ---------------------------------------------------------------------------
# AST node classes — simple containers for parsed data
# ---------------------------------------------------------------------------

class FormatDef:
    """
    The top-level AST node: one complete format definition.

    WHAT: Holds the format name and its list of fields.
    WHY:  Everything else in the compiler works with this tree.
    """

    def __init__(self, name, fields, line_number):
        self.name = name
        self.fields = fields            # list of Field objects
        self.line_number = line_number

    def __repr__(self):
        return "FormatDef({!r}, {} fields)".format(self.name, len(self.fields))


class Field:
    """
    One field inside a format (e.g. 'src_port: u16').

    WHAT: Holds the field name, its type, and the source line.
    WHY:  The code generator reads these to produce C struct members
          and parsing code.
    """

    def __init__(self, name, field_type, line_number):
        self.name = name
        self.field_type = field_type    # IntegerType or BytesType
        self.line_number = line_number

    def __repr__(self):
        return "Field({!r}, {!r})".format(self.name, self.field_type)


class IntegerType:
    """
    A fixed-size integer type like u8, u16, u32, u16le, or u32le.

    WHAT: Records which integer type a field has.
    WHY:  The code generator needs the type name to decide how many
          bytes to read and which byte order to use.
    """

    def __init__(self, type_name):
        self.type_name = type_name

    def __repr__(self):
        return "IntegerType({!r})".format(self.type_name)


class BytesType:
    """
    A variable-length byte array: bytes[EXPR].

    WHAT: Holds the expression that computes the byte count.
    WHY:  Unlike integer types, a bytes[] field has a size that
          depends on another field's value at runtime.
    """

    def __init__(self, size_expr):
        self.size_expr = size_expr      # NumberExpr, FieldRefExpr, or BinaryExpr

    def __repr__(self):
        return "BytesType({!r})".format(self.size_expr)


class NumberExpr:
    """
    A literal integer inside a size expression (e.g. the 8 in 'length - 8').

    WHAT: Wraps a plain integer value.
    WHY:  We need a node type for numbers so they can appear in
          expression trees alongside field references and operators.
    """

    def __init__(self, value):
        self.value = value              # a Python int

    def __repr__(self):
        return "NumberExpr({})".format(self.value)


class FieldRefExpr:
    """
    A reference to another field inside a size expression (e.g. 'length').

    WHAT: Stores the name of the referenced field and the source line.
    WHY:  The checker needs the field name to verify it exists, and
          the line number for error messages.
    """

    def __init__(self, field_name, line_number):
        self.field_name = field_name
        self.line_number = line_number

    def __repr__(self):
        return "FieldRefExpr({!r})".format(self.field_name)


class BinaryExpr:
    """
    A binary +/- expression like 'length - 8'.

    WHAT: A tree node with a left operand, an operator, and a right operand.
    WHY:  Size expressions can combine field references and numbers
          with addition and subtraction.
    """

    def __init__(self, left, operator, right):
        self.left = left                # NumberExpr, FieldRefExpr, or BinaryExpr
        self.operator = operator        # "+" or "-"
        self.right = right              # NumberExpr, FieldRefExpr, or BinaryExpr

    def __repr__(self):
        return "BinaryExpr({!r} {} {!r})".format(
            self.left, self.operator, self.right
        )


# ---------------------------------------------------------------------------
# Parse error
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when the parser encounters an unexpected token."""
    pass


# ---------------------------------------------------------------------------
# Parser class
# ---------------------------------------------------------------------------

class Parser:
    """
    Recursive-descent parser for the spec language.

    WHAT: Turns a list of tokens into an AST.
    WHY a class?  We need to keep track of the current position in the
    token list across several methods.  A class with self.position is
    the simplest way for a beginner to do that.
    """

    def __init__(self, token_list):
        self.token_list = token_list
        self.position = 0

    # --- Helper methods to move through the token list ----------------------

    def peek(self):
        """
        Return the current token WITHOUT advancing past it.

        WHAT: Lets us look ahead to decide which grammar rule to apply.
        WHY:  Many grammar decisions depend on what the next token is.
        """
        return self.token_list[self.position]

    def advance(self):
        """
        Return the current token AND move to the next one.

        WHAT: Consumes one token from the input.
        WHY:  After we decide what a token means, we move past it.
        """
        token = self.token_list[self.position]
        self.position = self.position + 1
        return token

    def expect(self, expected_type):
        """
        Check that the current token has the expected type, consume it,
        and return it.  If the type is wrong, raise a clear error.

        WHAT: Enforces a required token in the grammar.
        WHY:  Many grammar rules require a specific token (like LBRACE
              after the format name).  This helper keeps parsing methods
              short and gives the user a clear error message.
        """
        token = self.peek()
        if token.token_type != expected_type:
            raise ParseError(
                "Line {}: expected {} but found {} ({!r})".format(
                    token.line_number, expected_type,
                    token.token_type, token.value
                )
            )
        return self.advance()

    # --- Grammar rule methods -----------------------------------------------
    # Each method corresponds to one rule in the grammar at the top of
    # this file.  They call each other recursively — that is why this
    # technique is called "recursive descent."

    def parse(self):
        """
        Parse the whole input: one format definition followed by EOF.

        WHAT: Entry point for parsing.
        WHY:  We expect exactly one format per spec file.
        """
        format_node = self.parse_format_def()
        self.expect(EOF)
        return format_node

    def parse_format_def(self):
        """
        Parse:  FORMAT  IDENT  LBRACE  field*  RBRACE

        WHAT: Reads the format keyword, the name, and all fields
              between the braces.
        """
        format_token = self.expect(FORMAT)
        name_token = self.expect(IDENT)
        self.expect(LBRACE)

        field_list = []
        # Keep reading fields until we see the closing brace.
        while self.peek().token_type != RBRACE:
            field = self.parse_field()
            field_list.append(field)

        self.expect(RBRACE)
        return FormatDef(name_token.value, field_list, format_token.line_number)

    def parse_field(self):
        """
        Parse:  IDENT  COLON  type_spec

        WHAT: Reads one field name and its type.
        """
        name_token = self.expect(IDENT)
        self.expect(COLON)
        field_type = self.parse_type_spec()
        return Field(name_token.value, field_type, name_token.line_number)

    def parse_type_spec(self):
        """
        Parse a type: either  "bytes" LBRACKET size_expr RBRACKET
                    or  IDENT  (a fixed-size integer type).

        WHAT: Decides whether this is a bytes[] type or an integer type.
        WHY:  bytes[] types have a runtime-computed size, which needs
              special handling in the code generator.
        """
        type_token = self.expect(IDENT)

        # If the type name is "bytes", we require a [size_expr] after it.
        if type_token.value == "bytes":
            self.expect(LBRACKET)
            size_expr = self.parse_size_expr()
            self.expect(RBRACKET)
            return BytesType(size_expr)

        # Otherwise it is a plain integer type name like u16 or u32le.
        # The checker will verify it is a valid type name later.
        return IntegerType(type_token.value)

    def parse_size_expr(self):
        """
        Parse:  term  ((PLUS | MINUS) term)*

        WHAT: Reads an expression like 'length - 8' or just '4'.
        WHY:  The size of a bytes[] field can be a constant, a field
              reference, or a simple arithmetic expression using + and -.
              We parse left to right, building a tree of BinaryExpr nodes.
        """
        result = self.parse_term()

        # Handle chains of + and - (left to right).
        while self.peek().token_type in (PLUS, MINUS):
            operator_token = self.advance()
            right = self.parse_term()
            if operator_token.token_type == PLUS:
                operator_str = "+"
            else:
                operator_str = "-"
            result = BinaryExpr(result, operator_str, right)

        return result

    def parse_term(self):
        """
        Parse:  NUMBER | IDENT

        WHAT: Reads a single number literal or field-name reference.
        WHY:  These are the leaf nodes of size expressions.
        """
        token = self.peek()

        if token.token_type == NUMBER:
            self.advance()
            return NumberExpr(int(token.value))

        if token.token_type == IDENT:
            self.advance()
            return FieldRefExpr(token.value, token.line_number)

        raise ParseError(
            "Line {}: expected a number or field name but found {} ({!r})".format(
                token.line_number, token.token_type, token.value
            )
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def parse_tokens(token_list):
    """
    Parse a list of tokens and return a FormatDef AST node.

    WHAT: A simple wrapper so callers don't have to create a Parser
          object themselves.
    WHY:  Keeps the calling code in compiler.py short and clear.
    """
    parser = Parser(token_list)
    return parser.parse()
