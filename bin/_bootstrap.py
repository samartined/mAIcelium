"""Bootstrap helper: extends sys.path so bin/*.py can `from _lib import ...`.

Import this BEFORE any `_lib` import in scripts under bin/:

    import _bootstrap  # noqa: F401
    from _lib.workspace import load_workspace_section

Exposes WORKSPACE_ROOT for downstream consumers.
"""
import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

WORKSPACE_ROOT = os.path.dirname(_BIN_DIR)
