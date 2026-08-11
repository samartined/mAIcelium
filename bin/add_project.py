#!/usr/bin/env python3
"""Link a project repo into the mAIcelium workspace.

Usage: add_project.py [--code-only] <name> <path>

- Creates projects/<name> as a symlink to <path>.
- Imports project rules into .cursor/rules/<name>--<rulename> (unless --code-only).
- Imports project skills into .cursor/skills-cursor/<name>--<skillname> and
  .claude/skills/<name>--<skillname> (unless --code-only).
- Appends an entry under `projects:` in WORKSPACE.md.
- Regenerates .claude/projects-context.md and mAIcelium.code-workspace.

Python port of bin/add_project.sh.
"""
import _bootstrap  # noqa: F401

import datetime
import os
import re
import sys

from _lib.context import regenerate_claude_context, regenerate_workspace_file
from _lib.conventions import load_conventions
from _lib.platform import create_link, resolve_root
from _lib.workspace_writer import add_project_entry, create_workspace_template


NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _parse_args(argv):
    """Parse CLI args. Returns (code_only, name, repo_path) or exits on usage error."""
    code_only = False
    args = list(argv[1:])
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--code-only":
            code_only = True
        else:
            print(f"Unknown flag '{flag}'")
            sys.exit(1)

    if len(args) < 2:
        print("Usage: add_project.py [--code-only] <name> <path>")
        sys.exit(1)

    name = args[0]
    raw_path = args[1]
    try:
        repo_path = os.path.realpath(raw_path)
    except OSError:
        repo_path = ""

    return code_only, name, repo_path


def _check_registered(root, repo_path):
    """Warn (non-fatal) when repo_path is not present in repos/_registry.yaml."""
    registry = os.path.join(root, "repos", "_registry.yaml")
    if not os.path.isfile(registry):
        return

    home = os.path.expanduser("~")
    repo_path_home = repo_path
    if repo_path.startswith(home + os.sep) or repo_path == home:
        repo_path_home = "~" + repo_path[len(home):]

    try:
        with open(registry, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    if repo_path in content or repo_path_home in content:
        return

    print(f"Warning: '{repo_path}' is not registered in repos/_registry.yaml")
    print("   Consider adding it for agent discoverability.")


def _import_rules(root, name, repo_path, conventions):
    """Mirror each file under <repo>/<data_dir>/<rules_subdir> into .cursor/rules/."""
    rules_dir = os.path.join(
        repo_path,
        conventions["project_data_dir"],
        conventions["project_rules_subdir"],
    )
    if not os.path.isdir(rules_dir):
        return

    print("  -> Importing project rules...")
    target_dir = os.path.join(root, ".cursor", "rules")
    os.makedirs(target_dir, exist_ok=True)

    for entry in sorted(os.listdir(rules_dir)):
        src = os.path.join(rules_dir, entry)
        if not os.path.isfile(src):
            continue
        target = os.path.join(target_dir, f"{name}--{entry}")
        create_link(src, target)
        print(f"    + {name}--{entry}")
    print("  Project rules imported")


def _import_skills(root, name, repo_path, conventions):
    """Mirror skill directories from each configured skills subdir into the dotfolders.

    Targets .cursor/skills-cursor/ (Cursor) and .claude/skills/ (Claude Code's
    native skill directory) under the same `<name>--<skill>` flat name, so a
    freshly plugged-in project is discoverable in both without waiting for the
    next sync. remove_project.py prunes both via MIRROR_DIRS.
    """
    target_dirs = (
        os.path.join(root, ".cursor", "skills-cursor"),
        os.path.join(root, ".claude", "skills"),
    )
    for target_dir in target_dirs:
        os.makedirs(target_dir, exist_ok=True)

    for skills_subdir in conventions["project_skills_subdirs"]:
        skills_dir = os.path.join(
            repo_path,
            conventions["project_data_dir"],
            skills_subdir,
        )
        if not os.path.isdir(skills_dir):
            continue

        print(f"  -> Importing project skills ({skills_subdir}/)...")
        for entry in sorted(os.listdir(skills_dir)):
            src = os.path.join(skills_dir, entry)
            if not os.path.isdir(src):
                continue
            linked = False
            for target_dir in target_dirs:
                target = os.path.join(target_dir, f"{name}--{entry}")
                if os.path.islink(target):
                    continue
                create_link(src, target, target_is_directory=True)
                linked = True
            if linked:
                print(f"    + {name}--{entry}")
        print(f"  Project skills imported ({skills_subdir}/)")


def _update_workspace_md(root, name, repo_path):
    """Append/insert a project entry under `projects:` in WORKSPACE.md."""
    wf = os.path.join(root, "WORKSPACE.md")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    file_existed = os.path.isfile(wf)

    if not file_existed:
        # Create initial WORKSPACE.md with `created:` timestamp via writer.
        create_workspace_template(root, created=now)

    add_project_entry(root, name, repo_path, added=now)

    if not file_existed:
        print("  WORKSPACE.md created")
    else:
        print("  WORKSPACE.md updated")


def _list_active_projects(root):
    """Print current symlinks under projects/."""
    projects_dir = os.path.join(root, "projects")
    if not os.path.isdir(projects_dir):
        return
    print("")
    print("Active projects:")
    for entry in sorted(os.listdir(projects_dir)):
        link = os.path.join(projects_dir, entry)
        if os.path.islink(link):
            target = os.readlink(link)
            print(f"  {entry} -> {target}")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    code_only, name, repo_path = _parse_args(argv)

    if not name or not repo_path:
        print("Usage: add_project.py [--code-only] <name> <path>")
        return 1

    if not NAME_RE.match(name):
        print(
            f"Invalid project name '{name}'. "
            "Only letters, numbers, hyphens and underscores allowed."
        )
        return 1

    if not os.path.isdir(repo_path):
        print(f"Path '{repo_path}' does not exist.")
        return 1

    root = resolve_root()
    conventions = load_conventions(root)

    _check_registered(root, repo_path)

    projects_dir = os.path.join(root, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    link = os.path.join(projects_dir, name)

    if os.path.islink(link):
        print(f"Project '{name}' already exists. Use remove_project.py first.")
        return 1

    create_link(repo_path, link, target_is_directory=True)
    print(f"Project '{name}' added -> {repo_path}")

    os.makedirs(os.path.join(root, ".cursor", "rules"), exist_ok=True)
    os.makedirs(os.path.join(root, ".cursor", "skills-cursor"), exist_ok=True)
    os.makedirs(os.path.join(root, ".claude", "skills"), exist_ok=True)
    os.makedirs(os.path.join(root, ".agents", "rules"), exist_ok=True)
    os.makedirs(os.path.join(root, ".agents", "skills"), exist_ok=True)

    if not code_only:
        _import_rules(root, name, repo_path, conventions)
        _import_skills(root, name, repo_path, conventions)
    else:
        print("  Skipping rules/skills import (--code-only)")

    _update_workspace_md(root, name, repo_path)

    regenerate_claude_context(root)
    print("  Claude project context updated")

    regenerate_workspace_file(root)
    print("  Workspace file updated (mAIcelium.code-workspace)")

    _list_active_projects(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
