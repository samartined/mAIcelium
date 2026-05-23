#!/usr/bin/env python3
"""Remove a mesh layer from WORKSPACE.md and clean up its materializations.

Usage: remove_mesh_layer.py <name>

- Resolves the layer info from WORKSPACE.md (name -> client + path).
- Removes client--* symlinks from .cursor/{rules,skills-cursor}/ and
  .agents/{rules,skills}/ for the layer's client.
- Removes symlinks in mesh/{skills,rules}/_{common,domains,clients}/ that
  point into mesh/layers/<name>/.
- Drops the mesh/layers/<name> symlink (leaves real dirs alone with a warn).
- Strips the matching entry from `mesh_layers:` in WORKSPACE.md.
- Invokes sync_symlinks.main() to re-converge the workspace.

Python port of bin/remove_mesh_layer.sh.
"""
import _bootstrap  # noqa: F401

import argparse
import glob
import os
import sys

from _lib.platform import resolve_root
from _lib.workspace import load_workspace_section
import sync_symlinks


def _resolve_root():
    """Return MAICELIUM_ROOT env var if set, else the default workspace root."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    return resolve_root()


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="remove_mesh_layer.py",
        description="Remove a mesh layer from WORKSPACE.md and clean up its symlinks.",
    )
    parser.add_argument("name", help="Identifier of the layer to remove")
    return parser.parse_args(argv[1:])


def _print_registered_layers(root):
    """Best-effort listing of layers when the requested name is missing."""
    layers = load_workspace_section(root, "mesh_layers")
    print("Registered layers:")
    if not layers:
        print("  (none)")
        return
    for layer in layers:
        print(f"  - {layer['name']}  ->  {layer.get('path', '?')}")


def _find_layer(root, name):
    """Return (client, path) for the named layer, or (None, None) if absent."""
    for layer in load_workspace_section(root, "mesh_layers"):
        if layer.get("name") == name:
            return layer.get("client", layer["name"]), layer.get("path", "")
    return None, None


def _remove_client_symlinks(root, client):
    """Drop client--* symlinks from .cursor/{rules,skills-cursor}/ and .agents/{rules,skills}/."""
    targets = [
        (os.path.join(root, ".cursor", "rules"), "rule", ".cursor/rules/"),
        (os.path.join(root, ".agents", "rules"), "rule", ".agents/rules/"),
        (os.path.join(root, ".cursor", "skills-cursor"), "skill", ".cursor/skills-cursor/"),
        (os.path.join(root, ".agents", "skills"), "skill", ".agents/skills/"),
    ]
    for base, kind, label in targets:
        if not os.path.isdir(base):
            continue
        removed = 0
        for link in glob.glob(os.path.join(base, f"{client}--*")):
            if not os.path.islink(link):
                continue
            try:
                os.remove(link)
                removed += 1
            except OSError:
                continue
        if removed:
            print(f"  {removed} {kind} symlink(s) removed from {label}")


def _clean_mesh_mirrors(root, name, client):
    """Remove materialized symlinks under mesh/ that belong to this layer."""
    layer_dir = os.path.join(root, "mesh", "layers", name)
    try:
        layer_real = os.path.realpath(layer_dir) if os.path.exists(layer_dir) else None
    except OSError:
        layer_real = None

    removed = 0

    scan_dirs = [
        os.path.join(root, "mesh", "skills", "_common"),
        os.path.join(root, "mesh", "skills", "_domains"),
        os.path.join(root, "mesh", "rules", "_domains"),
    ]
    for base in scan_dirs:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            for entry in list(dirnames) + filenames:
                p = os.path.join(dirpath, entry)
                if not os.path.islink(p):
                    continue
                try:
                    target = os.path.realpath(p)
                except OSError:
                    continue
                if layer_real and target.startswith(layer_real + os.sep):
                    try:
                        os.remove(p)
                        removed += 1
                    except OSError:
                        continue

    # _clients/<client>/ — fully owned by this client
    for kind in ("skills", "rules"):
        client_dir = os.path.join(root, "mesh", kind, "_clients", client)
        if not os.path.isdir(client_dir):
            continue
        for entry in list(os.listdir(client_dir)):
            p = os.path.join(client_dir, entry)
            if os.path.islink(p):
                try:
                    target = os.path.realpath(p)
                except OSError:
                    target = ""
                if not layer_real or target.startswith(layer_real + os.sep):
                    try:
                        os.remove(p)
                        removed += 1
                    except OSError:
                        continue
        try:
            if not os.listdir(client_dir):
                os.rmdir(client_dir)
        except OSError:
            pass

    # Finally, mesh/layers/<name> itself
    if os.path.islink(layer_dir):
        try:
            os.remove(layer_dir)
            removed += 1
            print(f"  mesh/layers/{name} symlink removed")
        except OSError:
            pass
    elif os.path.isdir(layer_dir):
        print(f"  Warning: mesh/layers/{name} is a real directory - left in place")

    if removed:
        print(f"  {removed} mesh/ symlink(s) cleaned for layer '{name}'")


def _strip_workspace_entry(root, name):
    """Remove the `- name: <name>` block from `mesh_layers:` in WORKSPACE.md."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.exists(wf):
        print("  WORKSPACE.md does not exist, skipping")
        return

    with open(wf) as f:
        lines = f.readlines()

    out = []
    skip = False
    in_layers = False

    for line in lines:
        stripped = line.strip()

        if stripped == "mesh_layers:":
            in_layers = True
            out.append(line)
            continue

        if in_layers:
            # New top-level key terminates the section
            if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
                in_layers = False
                skip = False
                out.append(line)
                continue

            if stripped == f"- name: {name}":
                skip = True
                continue

            if skip and line.startswith("  "):
                continue
            skip = False

        out.append(line)

    with open(wf, "w") as f:
        f.writelines(out)

    print("  WORKSPACE.md updated")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = _parse_args(argv)
    name = args.name
    root = _resolve_root()

    client, layer_path = _find_layer(root, name)
    if client is None:
        print(f"Warning: Layer '{name}' not found in WORKSPACE.md.")
        _print_registered_layers(root)
        return 0

    print(f"Removing layer '{name}' (client: {client}, path: {layer_path})")

    _remove_client_symlinks(root, client)
    _clean_mesh_mirrors(root, name, client)
    _strip_workspace_entry(root, name)

    print(f"Layer '{name}' removed from workspace (repo at '{layer_path}' untouched)")

    rc = sync_symlinks.main([])
    if rc != 0:
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
