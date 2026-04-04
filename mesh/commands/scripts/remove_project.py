#!/usr/bin/env python3
"""Remove a project symlink from the mAIcelium workspace with fuzzy matching.

Usage: remove_project.py "<user_input>"

Resolves the project name against currently linked projects,
then delegates to bin/remove_project.py.
"""
import os
import sys

from fuzzy import fuzzy_match

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
PROJECTS_DIR = os.path.join(ROOT, "projects")
SKIP = {".gitkeep"}


def get_linked_projects():
    """Return sorted list of currently linked project names."""
    if not os.path.isdir(PROJECTS_DIR):
        return []
    return sorted(
        e
        for e in os.listdir(PROJECTS_DIR)
        if os.path.islink(os.path.join(PROJECTS_DIR, e)) and e not in SKIP
    )


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("❌ No project name provided.")
        linked = get_linked_projects()
        if linked:
            print(f"Linked projects: {', '.join(linked)}")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:]).strip()
    linked = get_linked_projects()

    if not linked:
        print("❌ No projects are currently linked.")
        sys.exit(1)

    match, candidates = fuzzy_match(user_input, linked)

    if not match and candidates:
        names = ", ".join(f"**{c}**" for c in candidates)
        print(f"❓ **{user_input}** is ambiguous: {names}")
        print("Please specify which one you meant.")
        sys.exit(2)

    if not match:
        print(f"❌ **{user_input}** is not linked.")
        print(f"Linked projects: {', '.join(linked)}")
        sys.exit(1)

    # Delegate to the Python script
    import subprocess

    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "bin", "remove_project.py"), match],
        capture_output=False,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
