#!/usr/bin/env python3
"""List all project symlinks in the mAIcelium workspace.

Usage: list_projects.py
"""
import os
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
PROJECTS_DIR = os.path.join(ROOT, "projects")
SKIP = {".gitkeep"}


def main():
    if not os.path.isdir(PROJECTS_DIR):
        print("📭 No projects directory found.")
        sys.exit(0)

    linked = sorted(
        e
        for e in os.listdir(PROJECTS_DIR)
        if os.path.islink(os.path.join(PROJECTS_DIR, e)) and e not in SKIP
    )

    if not linked:
        print("📭 No projects are currently linked.")
        sys.exit(0)

    print(f"📂 **{len(linked)}** linked project(s):")
    for name in linked:
        target = os.path.realpath(os.path.join(PROJECTS_DIR, name))
        exists = "✔" if os.path.isdir(target) else "✘ (broken)"
        print(f"  • **{name}** → {target} {exists}")


if __name__ == "__main__":
    main()
