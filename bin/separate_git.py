#!/usr/bin/env python3
"""Move the workspace .git directory to a sibling location and emit a shell wrapper.

Usage: separate_git.py [--help]

This is useful when you want to open the workspace in multiple IDEs and avoid
their internal git providers stepping on each other. After running this, use
`maicelium-git` (sourced from bin/.git-alias.sh) instead of `git` for workspace
operations.

Python port of bin/separate_git.sh. Idempotent: refuses to do anything
destructive if the git has already been separated.
"""
import _bootstrap  # noqa: F401

import os
import shutil
import sys

from _lib.platform import is_windows, resolve_root


HELP_TEXT = """Usage: separate_git.py [--help]

Move .git/ from the workspace to a sibling backup directory and create a
maicelium-git wrapper for operating on it.

The workspace root is detected automatically. After running this script:

  - .git/ is moved to <workspace>-git-backup/.git
  - A shell-alias file is written at bin/.git-alias.sh
  - On Windows, a PowerShell wrapper is written at
    Documents/PowerShell/maicelium-git.ps1
"""


def _print_help():
    print(HELP_TEXT)


def _write_unix_alias(alias_file, git_backup, root):
    """Write a posix shell alias file consumed via `source`."""
    content = (
        "# mAIcelium git alias - source this in your shell profile\n"
        "# Usage: maicelium-git <command>\n"
        "#\n"
        "# Example:\n"
        "#   maicelium-git status\n"
        "#   maicelium-git log --oneline\n"
        "#   maicelium-git add -A && maicelium-git commit -m \"msg\" && maicelium-git push\n"
        "#\n"
        f"alias maicelium-git='git --git-dir=\"{git_backup}/.git\" --work-tree=\"{root}\"'\n"
    )
    with open(alias_file, "w", encoding="utf-8") as f:
        f.write(content)


def _write_powershell_wrapper(ps_file, git_backup, root):
    """Write a PowerShell function wrapper. Caller must dot-source the file."""
    content = (
        "# mAIcelium git wrapper - dot-source this in your PowerShell profile\n"
        "# Usage: maicelium-git <command>\n"
        "function maicelium-git {\n"
        f"    git --git-dir=\"{git_backup}\\.git\" --work-tree=\"{root}\" @args\n"
        "}\n"
    )
    with open(ps_file, "w", encoding="utf-8") as f:
        f.write(content)


def _powershell_profile_dir():
    """Return the per-user PowerShell profile dir under Documents/PowerShell."""
    documents = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(documents, "PowerShell")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) > 1 and argv[1] in ("--help", "-h", "help"):
        _print_help()
        return 0

    root = resolve_root()
    basename = os.path.basename(root)
    git_backup = os.path.join(os.path.dirname(root), f"{basename}-git-backup")

    print("Separating .git from mAIcelium workspace")
    print(f"   Workspace: {root}")
    print(f"   Git backup: {git_backup}")
    print("")

    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        print(f"No .git directory found in {root}")
        print("   Either already separated or not a git repo.")
        return 1

    if os.path.isdir(git_backup):
        print(f"Backup directory already exists: {git_backup}")
        print("   Remove it first if you want to re-separate.")
        return 1

    created_backup = False
    try:
        os.makedirs(git_backup, exist_ok=False)
        created_backup = True
    except OSError as e:
        print(f"Could not create backup directory {git_backup}: {e}")
        return 1

    try:
        shutil.move(git_dir, os.path.join(git_backup, ".git"))
    except Exception as e:
        # Clean up the empty backup directory we just created so a subsequent
        # invocation does not abort with "Backup directory already exists".
        if created_backup:
            try:
                os.rmdir(git_backup)
            except OSError:
                pass
        print(f"Could not move .git: {e}")
        return 1
    print(f"  .git moved to {git_backup}/.git")

    alias_file = os.path.join(root, "bin", ".git-alias.sh")
    _write_unix_alias(alias_file, git_backup, root)
    print(f"  Shell alias created at {alias_file}")

    if is_windows():
        try:
            ps_dir = _powershell_profile_dir()
            os.makedirs(ps_dir, exist_ok=True)
            ps_file = os.path.join(ps_dir, "maicelium-git.ps1")
            _write_powershell_wrapper(ps_file, git_backup, root)
            print(f"  PowerShell wrapper created at {ps_file}")
        except OSError as e:
            print(f"  Could not write PowerShell wrapper: {e}")

    print("")
    print("Git separated successfully.")
    print("")
    print("Next steps:")
    print("  1. Add this to your shell profile (.bashrc / .zshrc):")
    print(f"     source \"{alias_file}\"")
    print("")
    print("  2. Use 'maicelium-git' instead of 'git' for workspace operations:")
    print("     maicelium-git status")
    print("     maicelium-git add -A && maicelium-git commit -m \"msg\"")
    print("     maicelium-git push")
    print("")
    print("  3. Or use the /git_backup command from within the IDE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
