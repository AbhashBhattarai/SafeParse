# compiler.py — Top-level compile function that ties all stages together.
#
# This module is the public API of SafeParse.  Both the command-line
# interface (cli.py) and the web app call compile_spec() to turn a
# spec string into C code.
#
# The pipeline is:  lex → parse → check → generate.

from safeparse.lexer import tokenize
from safeparse.parser import parse_tokens
from safeparse.checker import check_format
from safeparse.codegen import generate_c_code


def compile_spec(spec_text, mode="naive"):
    """
    Compile a spec string into C parser code.

    WHAT: Runs all four compiler stages in order and returns the result.
    WHY:  One function that does everything makes it easy for both the
          CLI and the web app to use the compiler without knowing the
          internal stages.

    Parameters:
        spec_text — the spec source code as a string
        mode      — "naive" or "optimized"

    Returns a dictionary with:
        "success"     — True if compilation succeeded, False if there were errors
        "errors"      — list of error-message strings (empty on success)
        "c_code"      — the generated C source code (empty on failure)
        "format_name" — the name from the format definition (empty on failure)
    """
    result = {
        "success": False,
        "errors": [],
        "c_code": "",
        "format_name": "",
    }

    # Stage 1: Lexing — turn source text into tokens.
    try:
        token_list = tokenize(spec_text)
    except SyntaxError as error:
        result["errors"].append(str(error))
        return result

    # Stage 2: Parsing — turn tokens into an AST.
    try:
        format_def = parse_tokens(token_list)
    except Exception as error:
        result["errors"].append(str(error))
        return result

    # Stage 3: Semantic checking — validate field names, types, references.
    errors = check_format(format_def)
    if errors:
        result["errors"] = errors
        return result

    # Stage 4: Code generation — produce C source code.
    c_code = generate_c_code(format_def, mode)

    result["success"] = True
    result["c_code"] = c_code
    result["format_name"] = format_def.name
    return result
