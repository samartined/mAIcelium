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
import os
import sys

from _lib.platform import resolve_root
from _lib.workspace_writer import set_mcp_source
import sync_symlinks


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
    set_mcp_source(root, src_path, repo=repo or None)
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

    root = resolve_root()
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
