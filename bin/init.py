#!/usr/bin/env python3
import os
import stat
from datetime import datetime, timezone

from _lib import resolve_root, is_windows, create_link

def make_executable(path):
    if not is_windows() and os.path.isfile(path):
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC)

def main():
    root = resolve_root()
    print(f"🍄 Initializing mAIcelium at: {root}")

    directories = [
        "mesh/skills/_common/code-review",
        "mesh/skills/_common/git-workflow",
        "mesh/skills/_common/testing",
        "mesh/skills/_common/planning",
        "mesh/skills/_common/documentation",
        "mesh/skills/_clients",
        "mesh/skills/_domains/frontend-react",
        "mesh/skills/_domains/backend-python",
        "mesh/skills/_domains/devops",
        "mesh/rules",
        "mesh/prompts",
        "mesh/commands",
        ".cursor/rules",
        ".cursor/skills-cursor",
        ".claude/commands",
        ".agents",
        "projects",
        "repos",
        "bin"
    ]
    for d in directories:
        os.makedirs(os.path.join(root, d), exist_ok=True)
        
    open(os.path.join(root, "projects", ".gitkeep"), 'a').close()
    open(os.path.join(root, "mesh", "skills", "_clients", ".gitkeep"), 'a').close()
    
    print("  → Creating symlinks via sync_symlinks...")
    import sync_symlinks
    sync_symlinks.main()
    
    settings_path = os.path.join(root, ".claude", "settings.json")
    if not os.path.isfile(settings_path):
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write('''{
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
      "Bash(python3:mesh/commands/scripts/*)",
      "Bash(python:bin/*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 bin/sync_symlinks.py > /dev/null 2>&1",
            "timeout": 5
          }
        ]
      }
    ]
  }
}''')
        print("  ✔ .claude/settings.json created")
    else:
        print("  ✔ .claude/settings.json already exists (kept)")

    workspace_path = os.path.join(root, "WORKSPACE.md")
    if not os.path.isfile(workspace_path):
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(workspace_path, "w", encoding="utf-8") as f:
            f.write(f"# Active workspace\n\nprojects: []\n\ncreated: {now_str}\n")
        print("  ✔ WORKSPACE.md created")
    else:
        print("  ✔ WORKSPACE.md already exists (kept)")

    registry = os.path.join(root, "repos", "_registry.yaml")
    template = os.path.join(root, "repos", "_registry.yaml.example")
    if not os.path.isfile(registry) and os.path.isfile(template):
        import shutil
        shutil.copy(template, registry)
        print("  ✔ repos/_registry.yaml created from template")

    if not is_windows():
        print("  → Creating smug symlink...")
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        smug_dir = os.path.join(config_home, "smug")
        os.makedirs(smug_dir, exist_ok=True)
        smug_link = os.path.join(smug_dir, "mAIcelium.yml")
        current_smug = os.path.join(root, ".smug.yml")
        create_link(current_smug, smug_link, target_is_directory=False)
        print("  ✔ smug symlink created")
        
        bin_dir = os.path.join(root, "bin")
        for f in os.listdir(bin_dir):
            if f.endswith(".sh") or f.endswith(".py"):
                make_executable(os.path.join(bin_dir, f))
        print("  ✔ Script permissions set")

    print("\n✅ mAIcelium initialized successfully.")
    print("   Next step: open this directory in your IDEs")

if __name__ == "__main__":
    main()
