"""Shared pytest marks for mAIcelium tests.

Import from here instead of conftest.py to avoid circular import issues:

    from _marks import requires_symlink
"""
import os
import sys

# Ensure bin/ is on sys.path so _lib.platform is importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import pytest


def _symlink_privilege():
    """Return True when this process can create symlinks.

    Honoring MAICELIUM_FORCE_NO_SYMLINK=1 lets CI simulate a Windows
    no-privilege environment without actually disabling symlinks.
    """
    if os.environ.get("MAICELIUM_FORCE_NO_SYMLINK") == "1":
        return False
    try:
        from _lib.platform import check_symlink_privilege
        return check_symlink_privilege()
    except Exception:
        return False


SYMLINK_OK = _symlink_privilege()

requires_symlink = pytest.mark.skipif(
    not SYMLINK_OK,
    reason="symlink creation requires privilege (Windows Developer Mode off)",
)
