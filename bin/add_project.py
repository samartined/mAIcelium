#!/usr/bin/env python3
import sys
import os
import re
from datetime import datetime, timezone
import argparse

from _lib import resolve_root, create_link, regenerate_workspace_file, regenerate_claude_context

def main():
    parser = argparse.ArgumentParser(description="Add project to mAIcelium workspace")
    parser.add_argument("--code-only", action="store_true")
    parser.add_argument("name", help="Name of the project")
    parser.add_argument("path", help="Path to the repository")
    args = parser.parse_args()

    root = resolve_root()
    name = args.name
    # Handle home expansion manually if needed, usually shell does it, but to be sure
    repo_path = os.path.realpath(os.path.expanduser(args.path))

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        print(f"❌ Invalid project name '{name}'. Only letters, numbers, hyphens and underscores allowed.")
        sys.exit(1)

    if not os.path.isdir(repo_path):
        print(f"❌ Path '{repo_path}' does not exist.")
        sys.exit(1)

    registry_path = os.path.join(root, "repos", "_registry.yaml")
    if os.path.isfile(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            registry_content = f.read()
        repo_path_home = repo_path.replace(os.path.expanduser("~"), "~")
        if repo_path not in registry_content and repo_path_home not in registry_content:
            print(f"⚠️  Warning: '{repo_path}' is not registered in repos/_registry.yaml")
            print("   Consider adding it for agent discoverability.")

    link = os.path.join(root, "projects", name)
    if os.path.islink(link) or os.path.exists(link):
        print(f"⚠️  Project '{name}' already exists. Use remove_project.py first.")
        sys.exit(1)

    try:
        create_link(repo_path, link, target_is_directory=True, check_privilege=True)
    except PermissionError as e:
        print(str(e))
        sys.exit(1)
        
    print(f"✔ Project '{name}' added → {repo_path}")

    if not args.code_only:
        p_rules_dir = os.path.join(repo_path, ".cursor", "rules")
        if os.path.isdir(p_rules_dir):
            print("  → Importing project rules...")
            for rule in os.listdir(p_rules_dir):
                rule_path = os.path.join(p_rules_dir, rule)
                if os.path.isfile(rule_path):
                    target = os.path.join(root, ".cursor", "rules", f"{name}--{rule}")
                    create_link(rule_path, target, target_is_directory=False)
                    print(f"    + {name}--{rule}")
            print("  ✔ Project rules imported")
            
        for skills_parent in [".cursor/skills", ".cursor/skills-cursor"]:
            p_skills_dir = os.path.join(repo_path, *skills_parent.split('/'))
            if os.path.isdir(p_skills_dir):
                print(f"  → Importing project skills ({skills_parent}/)...")
                for skill in os.listdir(p_skills_dir):
                    skill_dir = os.path.join(p_skills_dir, skill)
                    if os.path.isdir(skill_dir):
                        target = os.path.join(root, ".cursor", "skills-cursor", f"{name}--{skill}")
                        if not os.path.lexists(target):
                            create_link(skill_dir, target, target_is_directory=True)
                            print(f"    + {name}--{skill}")
                print("  ✔ Project skills imported")
    else:
        print("  ⏭ Skipping rules/skills import (--code-only)")

    # Update WORKSPACE.md
    wf = os.path.join(root, "WORKSPACE.md")
    if os.path.isfile(wf):
        with open(wf, "r", encoding="utf-8") as f:
            content = f.read()
        now_str = datetime.now(timezone.utc).isoformat()
        entry = f"- name: {name}\n  path: {repo_path}\n  added: {now_str}"
        if "projects: []" in content:
            content = content.replace("projects: []", f"projects:\n{entry}")
        else:
            content = content.rstrip() + f"\n{entry}\n"
        with open(wf, "w", encoding="utf-8") as f:
            f.write(content)
        print("  ✔ WORKSPACE.md updated")

    regenerate_claude_context(root)
    print("  ✔ Claude project context updated")

    regenerate_workspace_file(root)
    print("  ✔ Workspace file updated (mAIcelium.code-workspace)")

    print("\nActive projects:")
    projects_dir = os.path.join(root, "projects")
    for p in sorted(os.listdir(projects_dir)):
        p_link = os.path.join(projects_dir, p)
        if os.path.islink(p_link):
            try:
                target = os.readlink(p_link)
                print(f"l {p} -> {target}")
            except OSError:
                pass

if __name__ == "__main__":
    main()
