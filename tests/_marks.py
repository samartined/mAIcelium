"""Shared pytest marks for mAIcelium tests.

Import from here instead of conftest.py to avoid circular import issues:

    from _marks import requires_symlink
"""
import os
import sys
import warnings

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

    Import errors from _lib.platform propagate loudly (collection error)
    rather than silently masking failures as skips.
    """
    if os.environ.get("MAICELIUM_FORCE_NO_SYMLINK") == "1":
        return False
    # ImportError is intentionally NOT caught here so it propagates as a
    # collection error rather than a silent skip (TR-2).
    from _lib.platform import check_symlink_privilege
    try:
        return check_symlink_privilege()
    except OSError:
        return False
    except Exception as exc:
        warnings.warn(
            f"symlink privilege probe failed unexpectedly: {exc!r};"
            " treating as no-privilege",
            RuntimeWarning,
            stacklevel=2,
        )
        return False


SYMLINK_OK = _symlink_privilege()

requires_symlink = pytest.mark.skipif(
    not SYMLINK_OK,
    reason="symlink creation requires privilege (Windows Developer Mode off)",
)
