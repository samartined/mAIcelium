#!/usr/bin/env python3
"""Initialize the mAIcelium workspace.

Python port of bin/init.sh. Creates the standard directory tree, seeds
initial symlinks from mesh/ into .cursor/ and .agents/, drops template
files (WORKSPACE.md, .claude/settings.json, repos/_registry.yaml) when
missing, and regenerates the workspace + Claude context files.

Idempotent: running twice in a row is safe. Existing settings.json and
WORKSPACE.md are preserved.
"""
import _bootstrap  # noqa: F401

import datetime
import os
import stat
import sys

from _lib.context import regenerate_claude_context, regenerate_workspace_file
from _lib.platform import check_symlink_privilege, create_link, is_windows, resolve_root
from _lib.workspace_writer import create_workspace_template


_SETTINGS_JSON = """\
{
  "permissions": {
    "allow": [
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(find:*)",
      "Bash(realpath:*)",
      "Bash(ln:*)",
      "Bash(rm:*)",
      "Bash(mkdir:*)",
      "Bash(python3:bin/*)",
      "Bash(python3:bin/hooks/*)",
      "Bash(python3:mesh/commands/scripts/*)",
      "Bash(python:bin/*)",
      "Bash(python:bin/hooks/*)",
      "Bash(bin/py.sh:*)",
      "Bash(bin/py.cmd:*)",
      "Bash(bash:bin/*)",
      "Bash(bash:bin/hooks/*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bin/py.sh bin/sync_symlinks.py > /dev/null && echo \\"Context synced. Read .claude/projects-context.md for workspace and project rules.\\" || echo \\"sync_symlinks.py failed — context may be stale. Read .claude/projects-context.md.\\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bin/py.sh bin/hooks/guard_bash.py",
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bin/py.sh bin/hooks/guard_write.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
"""


# ── Directory layout ────────────────────────────────────────────────────────

_COMMON_SKILLS = [
    "code-review",
    "debug",
    "documentation",
    "git-workflow",
    "planning",
    "refactoring",
    "security-review",
    "testing",
    "workspace-guide",
]

_DOMAIN_SKILLS = [
    "frontend-react",
    "backend-python",
    "devops",
    "obsidian",
    "cursor",
]


def _create_directory_tree(root):
    """Create the canonical mAIcelium directory tree under root."""
    dirs = []

    # mesh/skills/_common/<skill>
    for skill in _COMMON_SKILLS:
        dirs.append(os.path.join(root, "mesh", "skills", "_common", skill))

    # mesh/skills/_clients (empty placeholder)
    dirs.append(os.path.join(root, "mesh", "skills", "_clients"))

    # mesh/skills/_domains/<domain>
    for domain in _DOMAIN_SKILLS:
        dirs.append(os.path.join(root, "mesh", "skills", "_domains", domain))

    # mesh/layers and other mesh subdirs
    dirs.append(os.path.join(root, "mesh", "layers"))
    for d in ("rules", "prompts", "commands"):
        dirs.append(os.path.join(root, "mesh", d))

    # Top-level workspace dirs
    dirs.append(os.path.join(root, ".cursor", "rules"))
    dirs.append(os.path.join(root, ".cursor", "skills-cursor"))
    dirs.append(os.path.join(root, ".claude", "commands"))
    dirs.append(os.path.join(root, ".agents"))
    dirs.append(os.path.join(root, "projects"))
    dirs.append(os.path.join(root, "repos"))
    dirs.append(os.path.join(root, "bin"))

    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # .gitkeep files for empty-but-tracked directories
    _touch(os.path.join(root, "mesh", "layers", ".gitkeep"))
    _touch(os.path.join(root, "projects", ".gitkeep"))
    _touch(os.path.join(root, "mesh", "skills", "_clients", ".gitkeep"))


def _touch(path):
    """Create an empty file if it does not exist; leave existing files alone."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8"):
        pass


# ── Initial symlinks (mesh/ -> .cursor/, .agents/) ──────────────────────────

def _create_cursor_symlinks(root):
    """Mirror mesh/rules/*.mdc and mesh/skills/{_common,_domains}/*/ into .cursor/."""
    print("  -> Creating Cursor symlinks...")

    cursor_rules = os.path.join(root, ".cursor", "rules")
    cursor_skills = os.path.join(root, ".cursor", "skills-cursor")
    os.makedirs(cursor_rules, exist_ok=True)
    os.makedirs(cursor_skills, exist_ok=True)

    # mesh/rules/*.mdc -> .cursor/rules/<name>
    rules_dir = os.path.join(root, "mesh", "rules")
    if os.path.isdir(rules_dir):
        for entry in sorted(os.listdir(rules_dir)):
            src = os.path.join(rules_dir, entry)
            if not os.path.isfile(src) or not entry.endswith(".mdc"):
                continue
            target = os.path.join(cursor_rules, entry)
            link_target = os.path.join("..", "..", "mesh", "rules", entry)
            create_link(link_target, target)

    # mesh/skills/_common/*/ -> .cursor/skills-cursor/<name>
    common_dir = os.path.join(root, "mesh", "skills", "_common")
    if os.path.isdir(common_dir):
        for entry in sorted(os.listdir(common_dir)):
            src = os.path.join(common_dir, entry)
            if not os.path.isdir(src):
                continue
            target = os.path.join(cursor_skills, entry)
            link_target = os.path.join("..", "..", "mesh", "skills", "_common", entry)
            create_link(link_target, target, target_is_directory=True)

    # mesh/skills/_domains/*/ -> .cursor/skills-cursor/<name>
    domains_dir = os.path.join(root, "mesh", "skills", "_domains")
    if os.path.isdir(domains_dir):
        for entry in sorted(os.listdir(domains_dir)):
            src = os.path.join(domains_dir, entry)
            if not os.path.isdir(src):
                continue
            target = os.path.join(cursor_skills, entry)
            link_target = os.path.join("..", "..", "mesh", "skills", "_domains", entry)
            create_link(link_target, target, target_is_directory=True)

    print("  OK Cursor symlinks created")


def _create_agents_symlinks(root):
    """Mirror mesh/rules, mesh/skills/_common, and mesh/commands into .agents/."""
    print("  -> Creating Antigravity (.agents/) symlinks...")

    agents_rules = os.path.join(root, ".agents", "rules")
    agents_skills = os.path.join(root, ".agents", "skills")
    agents_workflows = os.path.join(root, ".agents", "workflows")
    os.makedirs(agents_rules, exist_ok=True)
    os.makedirs(agents_skills, exist_ok=True)
    os.makedirs(agents_workflows, exist_ok=True)

    # mesh/rules/*.mdc -> .agents/rules/<name>
    rules_dir = os.path.join(root, "mesh", "rules")
    if os.path.isdir(rules_dir):
        for entry in sorted(os.listdir(rules_dir)):
            src = os.path.join(rules_dir, entry)
            if not os.path.isfile(src) or not entry.endswith(".mdc"):
                continue
            target = os.path.join(agents_rules, entry)
            link_target = os.path.join("..", "..", "mesh", "rules", entry)
            create_link(link_target, target)

    # mesh/skills/_common/*/ -> .agents/skills/<name>
    common_dir = os.path.join(root, "mesh", "skills", "_common")
    if os.path.isdir(common_dir):
        for entry in sorted(os.listdir(common_dir)):
            src = os.path.join(common_dir, entry)
            if not os.path.isdir(src):
                continue
            target = os.path.join(agents_skills, entry)
            link_target = os.path.join("..", "..", "mesh", "skills", "_common", entry)
            create_link(link_target, target, target_is_directory=True)

    # mesh/commands/*.md -> .agents/workflows/<name>
    commands_dir = os.path.join(root, "mesh", "commands")
    if os.path.isdir(commands_dir):
        for entry in sorted(os.listdir(commands_dir)):
            src = os.path.join(commands_dir, entry)
            if not os.path.isfile(src) or not entry.endswith(".md"):
                continue
            target = os.path.join(agents_workflows, entry)
            link_target = os.path.join("..", "..", "mesh", "commands", entry)
            create_link(link_target, target)

    print("  OK Antigravity (.agents/) symlinks created")


# ── Seed files ──────────────────────────────────────────────────────────────

def _create_settings_json(root):
    """Drop .claude/settings.json template only when missing (preserve manual edits)."""
    path = os.path.join(root, ".claude", "settings.json")
    if os.path.isfile(path):
        print("  OK .claude/settings.json already exists (kept)")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_SETTINGS_JSON)
    print("  OK .claude/settings.json created")


def _create_workspace_md(root):
    """Drop WORKSPACE.md template only when missing."""
    path = os.path.join(root, "WORKSPACE.md")
    if os.path.isfile(path):
        print("  OK WORKSPACE.md already exists (kept)")
        return
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    create_workspace_template(root, created=now)
    print("  OK WORKSPACE.md created")


def _create_registry_yaml(root):
    """Copy repos/_registry.yaml.example to repos/_registry.yaml only when missing."""
    src = os.path.join(root, "repos", "_registry.yaml.example")
    dst = os.path.join(root, "repos", "_registry.yaml")
    if os.path.isfile(dst):
        return
    if not os.path.isfile(src):
        return
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(data)
    print("  OK repos/_registry.yaml created from template")


# ── Platform-specific operations ────────────────────────────────────────────

def _create_smug_symlink(root):
    """Drop a smug symlink under ${XDG_CONFIG_HOME:-~/.config}/smug/. Linux/macOS only."""
    if is_windows():
        return

    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    smug_dir = os.path.join(xdg, "smug")
    print("  -> Creating smug symlink...")
    os.makedirs(smug_dir, exist_ok=True)
    src = os.path.join(root, ".smug.yml")
    dst = os.path.join(smug_dir, "mAIcelium.yml")
    create_link(src, dst)
    print("  OK smug symlink created")


def _chmod_scripts(root):
    """chmod +x bin/*.sh and bin/hooks/*.sh. Linux/macOS only."""
    if is_windows():
        return

    bin_dir = os.path.join(root, "bin")
    hooks_dir = os.path.join(bin_dir, "hooks")
    for d in (bin_dir, hooks_dir):
        if not os.path.isdir(d):
            continue
        for entry in os.listdir(d):
            if not entry.endswith(".sh"):
                continue
            full = os.path.join(d, entry)
            if not os.path.isfile(full):
                continue
            try:
                cur = os.stat(full).st_mode
                os.chmod(
                    full,
                    cur | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
                )
            except OSError:
                pass
    print("  OK Script permissions set")


# ── Entry point ─────────────────────────────────────────────────────────────

def main(root=None):
    """Initialize the workspace at root (defaults to resolve_root())."""
    if root is None:
        root = resolve_root()

    # Privilege check FIRST: on Windows without Developer Mode, symlink
    # creation fails. Abort cleanly before touching the filesystem so we
    # never leave a half-initialised workspace.
    if not check_symlink_privilege():
        sys.stderr.write(
            "Cannot create symbolic links. Enable Developer Mode on Windows "
            "(Settings -> System -> For developers -> Developer Mode), then re-run.\n"
        )
        return 2

    print(f"Initializing mAIcelium at: {root}")

    _create_directory_tree(root)
    _create_cursor_symlinks(root)
    _create_agents_symlinks(root)
    _create_settings_json(root)
    _create_workspace_md(root)
    _create_registry_yaml(root)
    _create_smug_symlink(root)
    _chmod_scripts(root)

    print("  -> Generating workspace file...")
    regenerate_workspace_file(root)
    print("  OK Workspace file created (mAIcelium.code-workspace)")

    print("  -> Generating Claude project context...")
    regenerate_claude_context(root)
    print("  OK Claude project context created")

    # Sync symlinks: materializes mesh layers, generates MCP configs,
    # regenerates workspace file and Claude context.
    import sync_symlinks
    sync_symlinks.main([])

    print("")
    print("mAIcelium initialized successfully.")
    print("   Next step: open this directory in your IDEs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
