#!/usr/bin/env python3
"""Sync symlinks across the workspace, generating IDE context."""
import os
import sys
import shutil

from _lib import (
    resolve_root,
    create_link,
    find_broken_symlinks,
    regenerate_claude_context,
    regenerate_workspace_file
)

def remove_broken_links(directory):
    broken = list(find_broken_symlinks(directory))
    if broken:
        print(f"⚠️  Removing broken symlinks in {os.path.relpath(directory, resolve_root())}/:")
        for link in broken:
            print(f"  - {os.path.basename(link)}")
            os.unlink(link)

def main():
    root = resolve_root()
    print("🔄 Syncing symlinks...")

    cursor_rules = os.path.join(root, ".cursor", "rules")
    cursor_skills = os.path.join(root, ".cursor", "skills-cursor")
    os.makedirs(cursor_rules, exist_ok=True)
    os.makedirs(cursor_skills, exist_ok=True)

    # 1. Clean broken symlinks
    remove_broken_links(cursor_rules)
    remove_broken_links(cursor_skills)

    # Note: we use relative paths for symlink targets where possible to maintain portability,
    # but the Python symlink creation logic can safely handle absolute paths if constructed carefully.
    # To mimic original behavior, we will use absolute paths for the source of create_link to be safe
    # and OS independent (create_link handles the translation to OS symlink API).

    # 2. Recreate mAIcelium global rules -> .cursor/rules/
    mesh_rules = os.path.join(root, "mesh", "rules")
    if os.path.isdir(mesh_rules):
        for entry in os.listdir(mesh_rules):
            if entry.endswith(".md"):
                source = os.path.join(mesh_rules, entry)
                target = os.path.join(cursor_rules, entry)
                create_link(source, target, target_is_directory=False, check_privilege=True)

    # 3. Recreate mAIcelium domain rules -> .cursor/rules/
    mesh_domain_rules = os.path.join(mesh_rules, "_domains")
    if os.path.isdir(mesh_domain_rules):
        for domain in os.listdir(mesh_domain_rules):
            domain_dir = os.path.join(mesh_domain_rules, domain)
            if not os.path.isdir(domain_dir):
                continue
            for rule in os.listdir(domain_dir):
                if rule.endswith(".md"):
                    source = os.path.join(domain_dir, rule)
                    target = os.path.join(cursor_rules, f"domain--{domain}--{rule}")
                    create_link(source, target, target_is_directory=False)

    # 4. Recreate mAIcelium global skills -> .cursor/skills-cursor/
    mesh_common_skills = os.path.join(root, "mesh", "skills", "_common")
    if os.path.isdir(mesh_common_skills):
        for skill in os.listdir(mesh_common_skills):
            skill_dir = os.path.join(mesh_common_skills, skill)
            if os.path.isdir(skill_dir):
                target = os.path.join(cursor_skills, skill)
                create_link(skill_dir, target, target_is_directory=True)

    # 5. Recreate mAIcelium domain skills
    mesh_domain_skills = os.path.join(root, "mesh", "skills", "_domains")
    if os.path.isdir(mesh_domain_skills):
        for domain in os.listdir(mesh_domain_skills):
            domain_dir = os.path.join(mesh_domain_skills, domain)
            if not os.path.isdir(domain_dir):
                continue
            if os.path.isfile(os.path.join(domain_dir, "SKILL.md")):
                target = os.path.join(cursor_skills, domain)
                create_link(domain_dir, target, target_is_directory=True)
            else:
                for skill in os.listdir(domain_dir):
                    skill_dir = os.path.join(domain_dir, skill)
                    if os.path.isdir(skill_dir):
                        target = os.path.join(cursor_skills, f"{domain}--{skill}")
                        create_link(skill_dir, target, target_is_directory=True)

    # 6. Recreate project-specific rules and skills
    projects_dir = os.path.join(root, "projects")
    if os.path.isdir(projects_dir):
        for project in os.listdir(projects_dir):
            project_link = os.path.join(projects_dir, project)
            if not os.path.isdir(project_link):
                continue
            repo_path = os.path.realpath(project_link)
            
            p_rules = os.path.join(repo_path, ".cursor", "rules")
            if os.path.isdir(p_rules):
                for rule in os.listdir(p_rules):
                    rule_path = os.path.join(p_rules, rule)
                    if os.path.isfile(rule_path):
                        target = os.path.join(cursor_rules, f"{project}--{rule}")
                        create_link(rule_path, target, target_is_directory=False)
            
            for skills_parent in [".cursor/skills", ".cursor/skills-cursor"]:
                p_skills = os.path.join(repo_path, *skills_parent.split('/'))
                if os.path.isdir(p_skills):
                    for skill in os.listdir(p_skills):
                        skill_dir = os.path.join(p_skills, skill)
                        if os.path.isdir(skill_dir):
                            target = os.path.join(cursor_skills, f"{project}--{skill}")
                            if not os.path.lexists(target):
                                create_link(skill_dir, target, target_is_directory=True)

    # 7. Antigravity (.agents/)
    legacy_ag = os.path.join(root, ".antigravity")
    if os.path.exists(legacy_ag):
        shutil.rmtree(legacy_ag, ignore_errors=True)
        
    agents_skills = os.path.join(root, ".agents", "skills")
    agents_workflows = os.path.join(root, ".agents", "workflows")
    os.makedirs(agents_skills, exist_ok=True)
    os.makedirs(agents_workflows, exist_ok=True)
    
    remove_broken_links(agents_skills)
    
    if os.path.isdir(mesh_common_skills):
        for skill in os.listdir(mesh_common_skills):
            skill_dir = os.path.join(mesh_common_skills, skill)
            if os.path.isdir(skill_dir):
                target = os.path.join(agents_skills, skill)
                create_link(skill_dir, target, target_is_directory=True)
                
    if os.path.isdir(mesh_domain_skills):
        for domain in os.listdir(mesh_domain_skills):
            domain_dir = os.path.join(mesh_domain_skills, domain)
            if not os.path.isdir(domain_dir):
                continue
            if os.path.isfile(os.path.join(domain_dir, "SKILL.md")):
                target = os.path.join(agents_skills, domain)
                create_link(domain_dir, target, target_is_directory=True)
            else:
                for skill in os.listdir(domain_dir):
                    skill_dir = os.path.join(domain_dir, skill)
                    if os.path.isdir(skill_dir):
                        target = os.path.join(agents_skills, f"{domain}--{skill}")
                        create_link(skill_dir, target, target_is_directory=True)
                        
    mesh_commands = os.path.join(root, "mesh", "commands")
    if os.path.isdir(mesh_commands):
        for cmd in os.listdir(mesh_commands):
            if cmd.endswith(".md"):
                source = os.path.join(mesh_commands, cmd)
                target = os.path.join(agents_workflows, cmd)
                create_link(source, target, target_is_directory=False)

    # 8. Regenerate Claude Code context
    regenerate_claude_context(root)
    
    # Ensure CLAUDE.md references project context
    claude_md = os.path.join(root, "CLAUDE.md")
    if os.path.isfile(claude_md):
        with open(claude_md, "r", encoding="utf-8") as f:
            content = f.read()
        if "projects-context.md" not in content:
            with open(claude_md, "a", encoding="utf-8") as f:
                f.write("\n## Project-specific context\nFor active project rules and skills, read `.claude/projects-context.md`.\n")
            print("  ✔ CLAUDE.md updated with project-context reference")

    # 9. Workspace file
    regenerate_workspace_file(root)
    print("  ✔ Workspace file regenerated")
    
    print("✅ Symlinks synced.")

if __name__ == "__main__":
    main()
