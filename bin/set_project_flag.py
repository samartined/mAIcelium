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
from _lib.workspace_writer import set_project_flag as _set_project_flag


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
    root = os.path.dirname(workspace_file)
    return _set_project_flag(root, project_name, flag_key, flag_value)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = _parse_args(argv)
    project = args.project
    flag = args.flag
    value = args.value

    root = resolve_root()
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
