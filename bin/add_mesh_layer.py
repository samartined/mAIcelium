#!/usr/bin/env python3
"""Register a mesh layer in WORKSPACE.md and sync symlinks.

Usage: add_mesh_layer.py <name> <path> [--client CLIENT] [--repo URL]

- Validates that <path> exists and is a directory.
- Warns (non-fatal) if <path>/rules and <path>/skills are both missing.
- Inserts a new entry under `mesh_layers:` in WORKSPACE.md (creates the
  section if absent). Duplicates within the section are detected and
  the script exits 0 with a warning instead of duplicating.
- Invokes sync_symlinks.main() in-process to materialize the layer.

Python port of bin/add_mesh_layer.sh.
"""
import _bootstrap  # noqa: F401

import argparse
import os
import sys

from _lib.platform import resolve_root
from _lib.workspace_writer import add_layer_entry
import sync_symlinks


def _parse_args(argv):
    """Parse CLI args. argparse handles usage/error formatting."""
    parser = argparse.ArgumentParser(
        prog="add_mesh_layer.py",
        description="Register a mesh layer in WORKSPACE.md and sync symlinks.",
    )
    parser.add_argument("name", help="Identifier for this layer (e.g. acme-corp)")
    parser.add_argument("path", help="Local path to the mesh layer repo")
    parser.add_argument(
        "--client",
        default="",
        help="Client name for rule/skill prefixing (defaults to <name>)",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Git remote URL (optional, for documentation)",
    )
    return parser.parse_args(argv[1:])


def _update_workspace(root, name, path, client, repo):
    """Insert/skip a mesh layer entry under `mesh_layers:` in WORKSPACE.md.

    Returns True if a write happened, False if a duplicate was detected
    (and the file was left untouched).
    """
    wrote = add_layer_entry(root, name, path, client=client, repo=repo or None)
    if wrote:
        print("  WORKSPACE.md updated")
    return wrote


def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = _parse_args(argv)
    name = args.name
    raw_path = args.path
    client = args.client
    repo = args.repo

    try:
        layer_path = os.path.realpath(raw_path)
    except OSError:
        layer_path = raw_path

    if not client:
        client = name

    if not os.path.isdir(layer_path):
        print(f"Path '{layer_path}' does not exist.")
        return 1

    # Warning (non-fatal) when neither rules/ nor skills/ exists
    if not os.path.isdir(os.path.join(layer_path, "rules")) and \
       not os.path.isdir(os.path.join(layer_path, "skills")):
        print(f"Warning: '{layer_path}' has no rules/ or skills/ directory.")

    root = resolve_root()
    _update_workspace(root, name, layer_path, client, repo)

    print(f"Mesh layer '{name}' added -> {layer_path} (client: {client})")

    print("  Running sync...")
    rc = sync_symlinks.main([])
    if rc != 0:
        return rc
    print("  Sync complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
