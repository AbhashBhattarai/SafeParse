# lexer.py — Turns spec source text into a flat list of tokens.
#
# Each token records its type (like IDENT or COLON), its text value,
# and the line number where it appeared.  The rest of the compiler
# works with tokens instead of raw characters, which makes parsing
# much simpler.


# ---------------------------------------------------------------------------
# Token type constants
# ---------------------------------------------------------------------------
# We use plain strings so they are easy to print and compare.

FORMAT   = "FORMAT"
LBRACE   = "LBRACE"
RBRACE   = "RBRACE"
COLON    = "COLON"
LBRACKET = "LBRACKET"
RBRACKET = "RBRACKET"
PLUS     = "PLUS"
MINUS    = "MINUS"
IDENT    = "IDENT"
NUMBER   = "NUMBER"
EOF      = "EOF"


# ---------------------------------------------------------------------------
# Token class
# ---------------------------------------------------------------------------

class Token:
    """
    One lexical token from the source text.

    WHAT: Stores the type, text value, and source line of a token.
    WHY:  The parser needs all three: the type to decide what grammar
          rule applies, the value for names and numbers, and the line
          number for error messages.
    """

    def __init__(self, token_type, value, line_number):
        self.token_type = token_type
        self.value = value
        self.line_number = line_number

    def __repr__(self):
        return "Token({}, {!r}, line={})".format(
            self.token_type, self.value, self.line_number
        )

    def __eq__(self, other):
        """Let us compare tokens in tests with == ."""
        if not isinstance(other, Token):
            return False
        return (self.token_type == other.token_type
                and self.value == other.value
                and self.line_number == other.line_number)


# ---------------------------------------------------------------------------
# Mapping from single characters to token types
# ---------------------------------------------------------------------------

SINGLE_CHAR_TOKENS = {
    "{": LBRACE,
    "}": RBRACE,
    ":": COLON,
    "[": LBRACKET,
    "]": RBRACKET,
    "+": PLUS,
    "-": MINUS,
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _is_ident_start(char):
    """Return True if *char* can begin an identifier (letter or underscore)."""
    return char.isalpha() or char == "_"


def _is_ident_char(char):
    """Return True if *char* can continue an identifier."""
    return char.isalnum() or char == "_"


# ---------------------------------------------------------------------------
# Main tokenize function
# ---------------------------------------------------------------------------

def tokenize(source_text):
    """
    Scan *source_text* and return a list of Token objects.

    WHAT: Walks through the source one character at a time, grouping
          characters into tokens.
    WHY:  The lexer is the first stage of the compiler.  It converts
          raw characters into tokens so the parser does not have to
          worry about whitespace, comments, or character-level details.
    """
    token_list = []
    position = 0
    line_number = 1
    length = len(source_text)

    while position < length:
        current_char = source_text[position]

        # --- Skip newlines (but count them for line numbers) -----------------
        if current_char == "\n":
            line_number = line_number + 1
            position = position + 1
            continue

        # --- Skip other whitespace -------------------------------------------
        if current_char in (" ", "\t", "\r"):
            position = position + 1
            continue

        # --- Skip line comments that start with # ---------------------------
        if current_char == "#":
            while position < length and source_text[position] != "\n":
                position = position + 1
            # Don't advance past the newline; the next loop iteration
            # will see it and increment line_number.
            continue

        # --- Single-character tokens (braces, colon, brackets, +, -) --------
        if current_char in SINGLE_CHAR_TOKENS:
            token_type = SINGLE_CHAR_TOKENS[current_char]
            token_list.append(Token(token_type, current_char, line_number))
            position = position + 1
            continue

        # --- Number literals (one or more digits) ----------------------------
        if current_char.isdigit():
            start = position
            while position < length and source_text[position].isdigit():
                position = position + 1
            number_text = source_text[start:position]
            token_list.append(Token(NUMBER, number_text, line_number))
            continue

        # --- Identifiers and keywords ----------------------------------------
        if _is_ident_start(current_char):
            start = position
            while position < length and _is_ident_char(source_text[position]):
                position = position + 1
            word = source_text[start:position]
            # "format" is the only keyword; everything else is an identifier.
            if word == "format":
                token_list.append(Token(FORMAT, word, line_number))
            else:
                token_list.append(Token(IDENT, word, line_number))
            continue

        # --- Anything else is an error ---------------------------------------
        raise SyntaxError(
            "Unexpected character {!r} on line {}".format(
                current_char, line_number
            )
        )

    # Always end with an EOF token so the parser knows when to stop.
    token_list.append(Token(EOF, "", line_number))
    return token_list
