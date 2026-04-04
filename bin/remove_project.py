#!/usr/bin/env python3
import sys
import os
import re

from _lib import resolve_root, regenerate_workspace_file, regenerate_claude_context

def main():
    if len(sys.argv) < 2:
        root_dir = resolve_root()
        print("Usage: remove_project.py <name>\n")
        print("Active projects:")
        projects_dir = os.path.join(root_dir, "projects")
        if os.path.isdir(projects_dir):
            for p in sorted(os.listdir(projects_dir)):
                p_link = os.path.join(projects_dir, p)
                if os.path.islink(p_link) and p != ".gitkeep":
                    print(f"  {p}")
        else:
            print("  (none)")
        sys.exit(1)

    name = sys.argv[1]
    
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        print(f"❌ Invalid project name '{name}'. Only letters, numbers, hyphens and underscores allowed.")
        sys.exit(1)

    root = resolve_root()
    link = os.path.join(root, "projects", name)
    if not (os.path.islink(link) or os.path.isdir(link)):
        print(f"❌ Project '{name}' does not exist in the workspace.")
        sys.exit(1)

    removed_rules = 0
    cursor_rules_dir = os.path.join(root, ".cursor", "rules")
    if os.path.isdir(cursor_rules_dir):
        for rule in os.listdir(cursor_rules_dir):
            if rule.startswith(f"{name}--"):
                rule_path = os.path.join(cursor_rules_dir, rule)
                if os.path.islink(rule_path) or os.path.isfile(rule_path):
                    os.unlink(rule_path)
                    print(f"  - {rule}")
                    removed_rules += 1
    if removed_rules > 0:
        print(f"  ✔ {removed_rules} project rule(s) removed")

    removed_skills = 0
    cursor_skills_dir = os.path.join(root, ".cursor", "skills-cursor")
    if os.path.isdir(cursor_skills_dir):
        for skill in os.listdir(cursor_skills_dir):
            if skill.startswith(f"{name}--"):
                skill_path = os.path.join(cursor_skills_dir, skill)
                if os.path.islink(skill_path) or os.path.isdir(skill_path):
                    try:
                        os.unlink(skill_path)
                    except OSError:
                        # might be junction (dir) instead of symlink
                        if os.path.isdir(skill_path):
                            import shutil
                            try:
                                shutil.rmtree(skill_path)
                            except OSError:
                                os.rmdir(skill_path)
                    print(f"  - {skill}")
                    removed_skills += 1
    if removed_skills > 0:
        print(f"  ✔ {removed_skills} project skill(s) removed")

    try:
        os.unlink(link)
    except OSError:
        if os.path.isdir(link):
             os.rmdir(link)
    print(f"✔ Project '{name}' removed from workspace (original repo untouched)")

    # Update WORKSPACE.md
    wf = os.path.join(root, "WORKSPACE.md")
    if os.path.isfile(wf):
        with open(wf, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        out = []
        skip = False
        for line in lines:
            if line.strip().startswith(f"- name: {name}"):
                skip = True
            elif skip and line.startswith("  "):
                continue
            else:
                skip = False
                out.append(line)
                
        with open(wf, "w", encoding="utf-8") as f:
            f.writelines(out)
        print("  ✔ WORKSPACE.md updated")

    regenerate_claude_context(root)
    print("  ✔ Claude project context updated")

    regenerate_workspace_file(root)
    print("  ✔ Workspace file updated (mAIcelium.code-workspace)")

if __name__ == "__main__":
    main()
