# __main__.py — Allows running SafeParse with: python -m safeparse
#
# WHY: This file makes the safeparse package executable as a module.
# When you type "python -m safeparse", Python looks for __main__.py.

from safeparse.cli import main

main()
