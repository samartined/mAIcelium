#!/usr/bin/env python3
"""Remove the registered MCP source from WORKSPACE.md and sync symlinks.

Usage: remove_mcp_source.py

- Reports the current `mcp_source.path` if any.
- Strips the `mcp_source:` block from WORKSPACE.md (and its trailing
  blank line companion, if present).
- Invokes sync_symlinks.main(), which unmounts mesh/mcp and regenerates
  empty MCP configs.

Python port of bin/remove_mcp_source.sh.
"""
import _bootstrap  # noqa: F401

import argparse
import os
import sys

from _lib.platform import resolve_root
from _lib.workspace import load_workspace_section
from _lib.workspace_writer import unset_mcp_source
import sync_symlinks


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="remove_mcp_source.py",
        description="Remove the registered MCP source from WORKSPACE.md and sync.",
    )
    parser.parse_args(argv[1:])


def _strip_workspace_block(root):
    """Strip the `mcp_source:` block from WORKSPACE.md (best-effort)."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.exists(wf):
        print("  WORKSPACE.md does not exist, skipping")
        return

    unset_mcp_source(root)
    print("  WORKSPACE.md updated")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    _parse_args(argv)
    root = resolve_root()

    current = load_workspace_section(root, "mcp_source")
    if not current:
        print("No MCP source is registered in WORKSPACE.md.")
    else:
        print(f"Removing MCP source (path: {current.get('path', '')})")

    # Remove the mesh/mcp symlink eagerly so sync sees a clean slate
    mcp_link = os.path.join(root, "mesh", "mcp")
    if os.path.islink(mcp_link):
        try:
            os.remove(mcp_link)
            print("  mesh/mcp symlink removed")
        except OSError:
            pass
    elif os.path.isdir(mcp_link):
        print("  Warning: mesh/mcp is a real directory - left untouched")

    _strip_workspace_block(root)

    print("  Running sync to regenerate IDE configs...")
    rc = sync_symlinks.main([])
    if rc != 0:
        return rc
    print("MCP source removed (external directory left untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
