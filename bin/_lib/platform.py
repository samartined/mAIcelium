"""Platform helpers for mAIcelium scripts.

Symlink creation requires Developer Mode (or admin) on Windows. These
helpers detect the privilege once per process and raise PermissionError
with actionable instructions when it is missing.
"""
import os
import platform
import tempfile
import uuid


def resolve_root():
    """Return the workspace root (two levels up from this file)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_windows():
    """True when running on Windows."""
    return platform.system() == "Windows"


def check_symlink_privilege():
    """Return True if the process can create symlinks.

    On non-Windows always True. On Windows, attempts a real symlink in
    tmpdir; failure means Developer Mode is OFF. Result is cached on the
    function object so the probe runs at most once per process.
    """
    if not is_windows():
        return True

    cached = getattr(check_symlink_privilege, "_cached", None)
    if cached is not None:
        return cached

    test_target = os.path.join(tempfile.gettempdir(), f"target_{uuid.uuid4().hex}")
    test_link = os.path.join(tempfile.gettempdir(), f"link_{uuid.uuid4().hex}")
    try:
        with open(test_target, "w") as f:
            f.write("test")
        os.symlink(test_target, test_link)
        os.remove(test_link)
        os.remove(test_target)
        check_symlink_privilege._cached = True
        return True
    except OSError:
        if os.path.exists(test_target):
            try:
                os.remove(test_target)
            except OSError:
                pass
        check_symlink_privilege._cached = False
        return False


_DEV_MODE_HINT = (
    "In Windows, this requires 'Developer Mode' to be enabled.\n"
    "Enable it: Settings -> System -> For developers -> Developer Mode.\n"
    "After enabling it, you may need to restart your terminal."
)


def create_link(source, target, target_is_directory=False, check_privilege=False):
    """Create a symlink at `target` pointing to `source`.

    Replaces any existing file/link at `target`. On Windows, surfaces
    winerror 1314/5 (privilege not held / access denied) as PermissionError
    with Developer Mode instructions. `target_is_directory` is honored only
    on Windows (POSIX symlinks are kind-agnostic at creation time).
    """
    if check_privilege and is_windows():
        if not check_symlink_privilege():
            raise PermissionError(
                f"Cannot create symbolic links.\n{_DEV_MODE_HINT}"
            )

    try:
        if os.path.islink(target) or os.path.lexists(target):
            os.unlink(target)
    except OSError:
        if os.path.isdir(target):
            try:
                os.rmdir(target)
            except OSError:
                pass

    try:
        if is_windows():
            os.symlink(source, target, target_is_directory=target_is_directory)
        else:
            os.symlink(source, target)
    except OSError as e:
        if is_windows() and getattr(e, "winerror", 0) in (1314, 5):
            raise PermissionError(
                f"Failed to create symlink at '{target}'.\n{_DEV_MODE_HINT}"
            ) from e
        raise
