#!/usr/bin/env python3
"""Set or update a flag on a project entry in WORKSPACE.md.

Usage:
    set_project_flag.py <project-name> <flag> <value>

Examples:
    set_project_flag.py maicelium-private context_inline false
    set_project_flag.py maicelium-private context_inline true

Supported flags:
    context_inline - when false, project is listed but rules/skills are not
                     inlined in .claude/projects-context.md (avoids duplication
                     from framework repos whose .cursor/ holds all mesh symlinks)

Python port of bin/set_project_flag.sh.
"""
import _bootstrap  # noqa: F401

import argparse
import os
import sys

from _lib.context import regenerate_claude_context
from _lib.platform import resolve_root


def _resolve_root():
    """Return MAICELIUM_ROOT env var if set, else the default workspace root."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    return resolve_root()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="set_project_flag.py",
        description="Set or update a flag on a project entry in WORKSPACE.md.",
    )
    parser.add_argument("project", help="Project name as registered under projects:")
    parser.add_argument("flag", help="Flag key, e.g. context_inline")
    parser.add_argument("value", help="Flag value, e.g. true/false")
    return parser.parse_args(argv[1:])


def _update_flag(workspace_file, project_name, flag_key, flag_value):
    """Insert or update `<flag_key>: <flag_value>` inside the project entry.

    Returns (action, error_msg). action is "added" | "updated" | None.
    If error_msg is non-empty, the file was not modified.
    """
    with open(workspace_file, encoding="utf-8") as f:
        lines = f.readlines()

    in_projects = False
    in_target = False
    target_end = None
    flag_line = None
    insert_after = None  # line index after which to insert the flag

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped == 'projects:':
            in_projects = True
            continue

        if not in_projects:
            continue

        # End of projects section
        if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
            if in_target:
                target_end = i
            break

        if stripped.startswith('- name:'):
            name = stripped.split(':', 1)[1].strip()
            if in_target and target_end is None:
                target_end = i
            in_target = (name == project_name)
            if in_target:
                insert_after = i

        if in_target:
            if stripped.startswith(f'{flag_key}:'):
                flag_line = i
            elif stripped and not stripped.startswith('#'):
                # Track last meaningful line of this entry for insertion point
                insert_after = i

    if not in_target and target_end is None:
        return None, f"project '{project_name}' not found in WORKSPACE.md"

    if flag_line is not None:
        # Update existing flag
        old = lines[flag_line]
        indent = len(old) - len(old.lstrip())
        lines[flag_line] = ' ' * indent + f'{flag_key}: {flag_value}\n'
        action = 'updated'
    else:
        # Insert new flag after the last line of this project entry
        indent = 2  # standard YAML list item indent
        new_line = ' ' * indent + f'{flag_key}: {flag_value}\n'
        lines.insert(insert_after + 1, new_line)
        action = 'added'

    with open(workspace_file, 'w', encoding="utf-8") as f:
        f.writelines(lines)

    return action, ""


def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = _parse_args(argv)
    project = args.project
    flag = args.flag
    value = args.value

    root = _resolve_root()
    workspace = os.path.join(root, "WORKSPACE.md")

    if not os.path.isfile(workspace):
        print(f"Error: WORKSPACE.md not found at {workspace}", file=sys.stderr)
        return 1

    action, err = _update_flag(workspace, project, flag, value)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    print(f"OK: {action} '{flag}: {value}' for project '{project}' in WORKSPACE.md")

    print("Regenerating context...")
    regenerate_claude_context(root)

    ctx_file = os.path.join(root, ".claude", "projects-context.md")
    try:
        with open(ctx_file, "rb") as f:
            data = f.read()
        line_count = data.count(b"\n")
        byte_count = len(data)
        print(f"Done. projects-context.md: {line_count} lines / {byte_count} bytes")
    except OSError:
        print("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
