#!/usr/bin/env python3
"""Register an external MCP source in WORKSPACE.md and sync symlinks.

Usage: add_mcp_source.py <path> [--repo URL]

- Validates that <path> exists and is a directory.
- Inserts (or replaces) the `mcp_source:` block in WORKSPACE.md so the
  block lives above `projects:` (ordering: mesh_layers -> mcp_source ->
  projects).
- Invokes sync_symlinks.main() to mount mesh/mcp and regenerate
  .mcp.json / .cursor/mcp.json / .agents/mcp.json.

Python port of bin/add_mcp_source.sh.
"""
import _bootstrap  # noqa: F401

import argparse
import datetime
import os
import sys

from _lib.platform import resolve_root
import sync_symlinks


def _resolve_root():
    """Return MAICELIUM_ROOT env var if set, else the default workspace root."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    return resolve_root()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="add_mcp_source.py",
        description="Register an external MCP source in WORKSPACE.md and sync.",
    )
    parser.add_argument(
        "path",
        help="Local path to the external MCP definitions directory",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Git remote URL (optional, documentation only)",
    )
    return parser.parse_args(argv[1:])


def _update_workspace(root, src_path, repo):
    """Insert or replace the `mcp_source:` block in WORKSPACE.md."""
    wf = os.path.join(root, "WORKSPACE.md")

    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not os.path.exists(wf):
        content = "# Active workspace\n\nprojects: []\n\ncreated: {}\n".format(now)
    else:
        with open(wf) as f:
            content = f.read()

    entry_lines = ["mcp_source:", f"  path: {src_path}"]
    if repo:
        entry_lines.append(f"  repo: {repo}")
    entry = "\n".join(entry_lines)

    lines = content.splitlines()
    new_lines = []
    i = 0
    replaced = False

    while i < len(lines):
        line = lines[i]
        if line.strip() == "mcp_source:":
            replaced = True
            new_lines.extend(entry.splitlines())
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_stripped = nxt.strip()
                if nxt and not nxt.startswith(' ') and not nxt.startswith('-') and nxt_stripped.endswith(':'):
                    break
                if nxt_stripped == '' and i + 1 < len(lines):
                    new_lines.append(nxt)
                    i += 1
                    break
                i += 1
            continue
        new_lines.append(line)
        i += 1

    if not replaced:
        # Insert mcp_source before projects: (order: mesh_layers -> mcp_source -> projects)
        final = []
        inserted = False
        for line in new_lines:
            if not inserted and line.strip() == "projects:":
                final.append(entry)
                final.append("")
                inserted = True
            final.append(line)
        if not inserted:
            final = new_lines + ["", entry, ""]
        new_lines = final

    output = "\n".join(new_lines)
    if not output.endswith("\n"):
        output += "\n"

    with open(wf, "w") as f:
        f.write(output)

    print(f"  WORKSPACE.md updated (mcp_source: {src_path})")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = _parse_args(argv)

    try:
        src_path = os.path.realpath(args.path)
    except OSError:
        src_path = args.path

    if not os.path.isdir(src_path):
        print(f"Path '{src_path}' does not exist or is not a directory.")
        return 1

    root = _resolve_root()
    _update_workspace(root, src_path, args.repo)

    print(f"MCP source registered -> {src_path}")

    print("  Running sync...")
    rc = sync_symlinks.main([])
    if rc != 0:
        return rc
    print("  Sync complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
