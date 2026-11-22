#!/usr/bin/env python3
"""Measure guard denials and heredoc use in Claude Code transcripts.

Reads the session transcripts under ``~/.claude/projects/*/*.jsonl`` (or the
directory given with ``--projects-dir``) and prints, per month:

- ``write_denied``: Write/Edit/MultiEdit/NotebookEdit calls a PreToolUse hook
  refused, and how many of those were perimeter denials ("outside the
  workspace");
- ``bash_denied``: Bash calls a PreToolUse hook refused;
- ``heredocs``: Bash commands that contain a heredoc (``<<`` / ``<<-``, not
  the ``<<<`` herestring).

By default only sessions whose working directory is this workspace (or a
folder inside it) are counted; ``--all`` counts every session.

It is the baseline and follow-up measure for decision 4 of the security model
(allow heredocs to files inside the write roots, then measure): run it before
and some weeks after the change and compare. Standard library only; it reads
transcripts and never writes anything.

Usage:
    bin/py.sh bin/hook_metrics.py [--since YYYY-MM] [--all] [--projects-dir DIR]
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_HOOK_ERROR = re.compile(r"^PreToolUse:(\w+) hook error: ")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?[A-Za-z_]")


def _workspace_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_under(path, root):
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def scan(projects_dir, workspace=None, since=None):
    """Return {month: counters} for the transcripts under *projects_dir*."""
    months = defaultdict(lambda: defaultdict(int))
    for path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        try:
            f = open(path, encoding="utf-8")
        except OSError:
            continue
        with f:
            in_scope = workspace is None
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict):
                    continue
                cwd = entry.get("cwd")
                if workspace is not None and isinstance(cwd, str) and cwd:
                    in_scope = _is_under(cwd, workspace)
                if not in_scope:
                    continue
                month = str(entry.get("timestamp", ""))[:7]
                if not month or (since and month < since):
                    continue
                message = entry.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, list):
                    continue
                counters = months[month]
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "tool_use" and item.get("name") == "Bash":
                        command = (item.get("input") or {}).get("command", "")
                        if isinstance(command, str) and _HEREDOC.search(command):
                            counters["heredocs"] += 1
                    elif item.get("type") == "tool_result":
                        m = _HOOK_ERROR.match(_text(item.get("content")))
                        if not m:
                            continue
                        if m.group(1) in _WRITE_TOOLS:
                            counters["write_denied"] += 1
                            if "outside the workspace" in _text(item.get("content")):
                                counters["write_denied_outside"] += 1
                        elif m.group(1) == "Bash":
                            counters["bash_denied"] += 1
    return months


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--projects-dir", default=os.path.expanduser(os.path.join("~", ".claude", "projects")))
    parser.add_argument("--since", help="first month to count, as YYYY-MM")
    parser.add_argument("--all", action="store_true", help="count sessions outside this workspace too")
    args = parser.parse_args(argv)

    workspace = None if args.all else _workspace_root()
    months = scan(args.projects_dir, workspace=workspace, since=args.since)
    cols = ("write_denied", "write_denied_outside", "bash_denied", "heredocs")
    print("month    " + "  ".join(f"{c:>20}" for c in cols))
    for month in sorted(months):
        print(f"{month}  " + "  ".join(f"{months[month][c]:>20}" for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
