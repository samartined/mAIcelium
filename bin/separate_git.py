#!/usr/bin/env python3
import sys
import os
import shutil

from _lib import resolve_root, is_windows

def main():
    root = resolve_root()
    basename = os.path.basename(root)
    git_backup = f"{root}-git-backup"
    
    print("🍄 Separating .git from mAIcelium workspace")
    print(f"   Workspace: {root}")
    print(f"   Git backup: {git_backup}\n")

    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        print(f"❌ No .git directory found in {root}")
        print("   Either already separated or not a git repo.")
        sys.exit(1)

    if os.path.isdir(git_backup):
        print(f"❌ Backup directory already exists: {git_backup}")
        print("   Remove it first if you want to re-separate.")
        sys.exit(1)

    os.makedirs(git_backup, exist_ok=True)
    shutil.move(git_dir, os.path.join(git_backup, ".git"))
    print(f"  ✔ .git moved to {git_backup}/.git")

    alias_file = os.path.join(root, "bin", ".git-alias.sh")
    with open(alias_file, "w", encoding="utf-8") as f:
        f.write(f"""# mAIcelium git alias — source this in your shell profile
# Usage: maicelium-git <command>
#
# Example:
#   maicelium-git status
#   maicelium-git log --oneline
#   maicelium-git add -A && maicelium-git commit -m "msg" && maicelium-git push
#
alias maicelium-git='git --git-dir="{git_backup}/.git" --work-tree="{root}"'
""")
    print(f"  ✔ Shell alias created at {alias_file}")

    if is_windows():
        ps1_file = os.path.join(root, "bin", "maicelium-git.ps1")
        with open(ps1_file, "w", encoding="utf-8") as f:
             f.write(f"""# mAIcelium git wrapper for PowerShell
# Add {os.path.join(root, 'bin')} to your PATH to use this command directly
git --git-dir="{git_backup}\\.git" --work-tree="{root}" $args
""")
        print(f"  ✔ PowerShell wrapper created at {ps1_file}")

    print("\n✅ Git separated successfully.\n")
    print("Next steps:")
    if is_windows():
         print("  1. Add the bin folder to your PATH (or run bin\\maicelium-git.ps1 directly).")
    else:
         print(f"  1. Add this to your shell profile (.bashrc / .zshrc):\n     source \"{alias_file}\"\n")
    
    print("  2. Use 'maicelium-git' instead of 'git' for workspace operations:")
    print("     maicelium-git status")
    print("     maicelium-git add -A && maicelium-git commit -m \"msg\"")
    print("     maicelium-git push\n")
    print("  3. Or use the /git_backup command from within the IDE.")

if __name__ == "__main__":
    main()
