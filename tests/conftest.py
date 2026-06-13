"""Shared pytest fixtures and sys.path setup for mAIcelium tests."""
import os
import sys

# Make bin/ importable so tests can `from _lib.workspace import ...`
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

# Also make tests/ importable so test modules can do `from _marks import requires_symlink`.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Re-export the mark so anything that has conftest on its path can also reach it.
from _marks import SYMLINK_OK, requires_symlink  # noqa: F401, E402
