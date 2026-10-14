# conftest.py — Pytest configuration for the SafeParse project.
#
# WHY: Makes sure Python can find the safeparse package when running
# tests from the project root directory.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
