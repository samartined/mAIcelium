"""Symlink discovery and diagnostics for mAIcelium scripts."""
import os

from _lib.platform import is_windows


def find_broken_symlinks(directory, maxdepth=None):
    """Return list of dangling symlinks under `directory`.

    maxdepth: None for unlimited; an integer caps traversal depth where
    depth 0 is `directory` itself. Used by the mesh mirror cleanup which
    only scans the first 3 levels.
    """
    if not os.path.isdir(directory):
        return []

    base = os.path.abspath(directory)
    base_depth = base.rstrip(os.sep).count(os.sep)
    broken = []

    for root, dirs, files in os.walk(base):
        if maxdepth is not None:
            current_depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if current_depth >= maxdepth:
                dirs[:] = []

        for name in list(dirs) + files:
            full_path = os.path.join(root, name)
            if not os.path.islink(full_path):
                continue
            target = os.readlink(full_path)
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(full_path), target)
            if not os.path.exists(target):
                broken.append(full_path)

    return broken


def detect_junction(path):
    """True if `path` is a Windows directory junction. Always False on Linux."""
    if not is_windows():
        return False
    try:
        st = os.lstat(path)
        return bool(getattr(st, "st_reparse_tag", 0))
    except OSError:
        return False
