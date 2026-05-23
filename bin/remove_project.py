#!/usr/bin/env python3
"""Remove a project symlink from the mAIcelium workspace.

Usage: remove_project.py <name>

- Removes mirror symlinks <name>--* under .cursor/{rules,skills,skills-cursor}
  and .agents/{rules,skills}.
- Removes the projects/<name> symlink.
- Removes the .agents/projects/<name>/ tree (symlinks-only, no real data).
- Strips the matching `- name: <name>` block from WORKSPACE.md.
- Regenerates .claude/projects-context.md and mAIcelium.code-workspace.

Python port of bin/remove_project.sh.
"""
import _bootstrap  # noqa: F401

import os
import re
import shutil
import sys

from _lib.context import regenerate_claude_context, regenerate_workspace_file
from _lib.platform import resolve_root


NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

MIRROR_DIRS = (
    (".cursor", "rules"),
    (".cursor", "skills"),
    (".cursor", "skills-cursor"),
    (".agents", "rules"),
    (".agents", "skills"),
)


def _list_linked(root):
    """Return list of currently linked project names under projects/."""
    projects_dir = os.path.join(root, "projects")
    if not os.path.isdir(projects_dir):
        return []
    return sorted(
        e for e in os.listdir(projects_dir)
        if os.path.islink(os.path.join(projects_dir, e))
    )


def _remove_mirrors(root, name):
    """Remove every <name>--* symlink under the mirror directories."""
    prefix = f"{name}--"

    for dir_parts in MIRROR_DIRS:
        mirror_dir = os.path.join(root, *dir_parts)
        if not os.path.isdir(mirror_dir):
            continue

        removed = 0
        for entry in sorted(os.listdir(mirror_dir)):
            if not entry.startswith(prefix):
                continue
            full = os.path.join(mirror_dir, entry)
            if not os.path.islink(full):
                continue
            try:
                os.unlink(full)
            except OSError as e:
                print(f"  Could not remove {full}: {e}")
                continue
            print(f"  - {entry}")
            removed += 1

        if removed > 0:
            kind = "/".join(dir_parts)
            print(f"  {removed} symlink(s) removed from {kind}/")


def _remove_entry_lines(lines, target_name):
    """Remove the `- name: target_name` entry and all its indented continuation,
    including blank lines that are part of the entry block.

    A blank line belongs to the entry when the next non-blank line is indented
    (starts with a space or tab).  Once a non-blank, non-indented line follows,
    the entry has ended and the blank separators are kept.
    """
    out = []
    skip = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if skip:
            # Indented line -> still inside the entry block.
            if line.startswith(" ") or line.startswith("\t"):
                i += 1
                continue

            if stripped == "":
                # Look ahead to the first non-blank line.
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines) and (
                    lines[j].startswith(" ") or lines[j].startswith("\t")
                ):
                    # The blank lines belong to the entry; skip past them.
                    i = j
                    continue
                # The entry has ended; the blank line is a separator, keep it.
                skip = False
                out.append(line)
                i += 1
                continue

            # Non-blank, non-indented line: the entry has ended.
            skip = False

        if stripped == f"- name: {target_name}":
            skip = True
            i += 1
            continue

        out.append(line)
        i += 1
    return out


def _remove_workspace_entry(root, name):
    """Strip the `- name: <name>` block from WORKSPACE.md, preserving everything else."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.isfile(wf):
        print("  WORKSPACE.md does not exist, skipping")
        return

    with open(wf, encoding="utf-8") as f:
        lines = f.readlines()

    out = _remove_entry_lines(lines, name)

    with open(wf, "w", encoding="utf-8") as f:
        f.writelines(out)
    print("  WORKSPACE.md updated")


def _remove_agents_project_tree(root, name):
    """Remove .agents/projects/<name>/ entirely (it only contains symlinks)."""
    target = os.path.join(root, ".agents", "projects", name)
    if os.path.exists(target) or os.path.islink(target):
        shutil.rmtree(target, ignore_errors=True)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) < 2 or not argv[1].strip():
        print("Usage: remove_project.py <name>")
        root = resolve_root()
        linked = _list_linked(root)
        print("")
        print("Active projects:")
        if linked:
            for p in linked:
                print(f"  {p}")
        else:
            print("  (none)")
        return 1

    name = argv[1].strip()
    if not NAME_RE.match(name):
        print(
            f"Invalid project name '{name}'. "
            "Only letters, numbers, hyphens and underscores allowed."
        )
        return 1

    root = resolve_root()
    link = os.path.join(root, "projects", name)

    if not os.path.islink(link):
        print(f"Project '{name}' does not exist in the workspace.")
        return 1

    _remove_mirrors(root, name)

    try:
        os.unlink(link)
    except OSError as e:
        print(f"Could not remove projects/{name}: {e}")
        return 1
    print(f"Project '{name}' removed from workspace (original repo untouched)")

    _remove_agents_project_tree(root, name)

    _remove_workspace_entry(root, name)

    regenerate_claude_context(root)
    print("  Claude project context updated")

    regenerate_workspace_file(root)
    print("  Workspace file updated (mAIcelium.code-workspace)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
