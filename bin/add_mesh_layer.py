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
    wf = os.path.join(root, "WORKSPACE.md")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not os.path.exists(wf):
        content = "# Active workspace\n\nprojects: []\n\ncreated: {}\n".format(now)
    else:
        with open(wf, encoding="utf-8") as f:
            content = f.read()

    # Build entry
    entry_lines = [f"- name: {name}", f"  path: {path}", f"  client: {client}"]
    if repo:
        entry_lines.append(f"  repo: {repo}")
    entry = "\n".join(entry_lines)

    # Check for duplicate within mesh_layers section only
    in_layers = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "mesh_layers:":
            in_layers = True
            continue
        if in_layers:
            if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
                break
            if stripped == f"- name: {name}":
                print(f"  Warning: Layer '{name}' already exists in WORKSPACE.md")
                return False

    # Insert into mesh_layers section or create it
    if "mesh_layers:" in content:
        # Find end of mesh_layers block and append there
        lines = content.splitlines()
        insert_at = None
        in_layers = False
        for i, line in enumerate(lines):
            if line.strip() == "mesh_layers:":
                in_layers = True
                continue
            if in_layers:
                if line and not line.startswith(' ') and not line.startswith('-') and line.strip().endswith(':'):
                    insert_at = i
                    break
        if insert_at is None:
            # mesh_layers is the last section
            content = content.rstrip() + "\n" + entry + "\n"
        else:
            lines.insert(insert_at, entry)
            content = "\n".join(lines) + "\n"
    else:
        # Prepend mesh_layers before projects:
        if "projects:" in content:
            content = content.replace("projects:", f"mesh_layers:\n{entry}\n\nprojects:", 1)
        else:
            content = f"mesh_layers:\n{entry}\n\n" + content

    with open(wf, "w", encoding="utf-8") as f:
        f.write(content)
    print("  WORKSPACE.md updated")
    return True


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

    root = _resolve_root()
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
