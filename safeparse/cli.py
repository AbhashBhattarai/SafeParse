# cli.py — Command-line interface for the SafeParse compiler.
#
# Usage:
#   python -m safeparse specs/udp.spec
#   python -m safeparse specs/udp.spec --mode optimized
#   python -m safeparse specs/udp.spec --mode optimized --output parser.c
#
# Reads a .spec file, compiles it, and prints or saves the generated C code.

import sys
from safeparse.compiler import compile_spec


def read_file(file_path):
    """
    Read and return the entire contents of a text file.

    WHAT: Opens a file and reads all of it into a string.
    WHY:  We need to load the spec file before we can compile it.
    """
    with open(file_path, "r") as file_handle:
        return file_handle.read()


def write_file(file_path, content):
    """
    Write a string to a text file (creates or overwrites).

    WHAT: Saves text to a file on disk.
    WHY:  Used to save the generated C code when --output is given.
    """
    with open(file_path, "w") as file_handle:
        file_handle.write(content)


def parse_arguments(arg_list):
    """
    Parse command-line arguments manually.

    WHAT: Walks through the argument list and extracts the spec file
          path, mode, and output path.
    WHY:  We keep it simple — no external library needed for just
          three possible arguments.
    """
    options = {
        "spec_file": None,
        "mode": "naive",
        "output": None,
    }

    index = 0
    while index < len(arg_list):
        arg = arg_list[index]

        if arg == "--mode" and index + 1 < len(arg_list):
            options["mode"] = arg_list[index + 1]
            index = index + 2
        elif arg == "--output" and index + 1 < len(arg_list):
            options["output"] = arg_list[index + 1]
            index = index + 2
        elif arg.startswith("--"):
            print("Unknown option: {}".format(arg))
            sys.exit(1)
        else:
            # Positional argument = spec file path
            options["spec_file"] = arg
            index = index + 1

    return options


def main():
    """
    Entry point for the SafeParse CLI.

    WHAT: Reads arguments, compiles the spec, and outputs the C code.
    WHY:  This is how users run SafeParse from the terminal.
    """
    arg_list = sys.argv[1:]

    if not arg_list:
        print("Usage: python -m safeparse <spec_file> "
              "[--mode naive|optimized] [--output <file>]")
        sys.exit(1)

    options = parse_arguments(arg_list)

    if options["spec_file"] is None:
        print("Error: no spec file specified")
        sys.exit(1)

    if options["mode"] not in ("naive", "optimized"):
        print("Error: mode must be 'naive' or 'optimized', "
              "got {!r}".format(options["mode"]))
        sys.exit(1)

    # Read the spec file.
    spec_text = read_file(options["spec_file"])

    # Compile it.
    result = compile_spec(spec_text, options["mode"])

    if not result["success"]:
        print("Compilation failed with {} error(s):".format(
            len(result["errors"])
        ))
        for error_message in result["errors"]:
            print("  " + error_message)
        sys.exit(1)

    # Output the generated C code.
    if options["output"]:
        write_file(options["output"], result["c_code"])
        print("Generated C code written to: {}".format(options["output"]))
    else:
        print(result["c_code"])


if __name__ == "__main__":
    main()
