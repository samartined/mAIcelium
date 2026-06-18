#!/usr/bin/env python3
"""List all project symlinks in the mAIcelium workspace.

Usage: list_projects.py
"""
import os
import sys

SKIP = {".gitkeep"}


def _get_root():
    """Resolve workspace root. Allow override via MAICELIUM_ROOT for tests."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    # mesh/commands/scripts/list_projects.py -> root is 4 levels up from this file
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def _safe_stdout():
    """Reconfigure stdout to survive cp1252/latin-1 consoles without crashing."""
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def main():
    _safe_stdout()
    root = _get_root()
    projects_dir = os.path.join(root, "projects")

    if not os.path.isdir(projects_dir):
        print("📭 No projects directory found.")
        sys.exit(0)

    linked = sorted(
        e
        for e in os.listdir(projects_dir)
        if os.path.islink(os.path.join(projects_dir, e)) and e not in SKIP
    )

    if not linked:
        print("📭 No projects are currently linked.")
        sys.exit(0)

    print(f"📂 **{len(linked)}** linked project(s):")
    for name in linked:
        target = os.path.realpath(os.path.join(projects_dir, name))
        exists = "✔" if os.path.isdir(target) else "✘ (broken)"
        print(f"  • **{name}** → {target} {exists}")


if __name__ == "__main__":
    main()
