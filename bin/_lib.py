#!/usr/bin/env python3
"""Shared functions for mAIcelium scripts."""
import json
import os
import sys
import platform
import subprocess

def resolve_root():
    """Resolve the root of the mAIcelium workspace."""
    # This file is in bin/_lib.py, so root is two levels up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def is_windows():
    """Check if the current platform is Windows."""
    return platform.system() == "Windows"

def check_symlink_privilege():
    """Check if the process has privileges to create symlinks in Windows."""
    import tempfile
    import uuid
    if not is_windows():
        return True
    
    test_target = os.path.join(tempfile.gettempdir(), f"target_{uuid.uuid4().hex}")
    test_link = os.path.join(tempfile.gettempdir(), f"link_{uuid.uuid4().hex}")
    try:
        with open(test_target, "w") as f:
            f.write("test")
        os.symlink(test_target, test_link)
        os.remove(test_link)
        os.remove(test_target)
        return True
    except OSError:
        if os.path.exists(test_target):
            os.remove(test_target)
        return False

def create_link(source, target, target_is_directory=False, check_privilege=False):
    """
    Create a symlink at `target` pointing to `source`.
    If the link already exists and points somewhere else, it's replaced.
    Raises an error with clear instructions on Windows if Developer Mode is missing.
    """
    if check_privilege and is_windows() and getattr(create_link, "privilege_checked", False) is False:
        if not check_symlink_privilege():
             raise PermissionError(
                "❌ Cannot create symbolic links.\n"
                "In Windows, this requires 'Developer Mode' to be enabled.\n"
                "Please enable Developer Mode: Settings -> System -> For developers -> Developer Mode.\n"
                "After enabling it, you may need to restart your terminal."
             )
        create_link.privilege_checked = True

    try:
        if os.path.islink(target) or os.path.lexists(target):
            os.unlink(target)
    except OSError:
        # Might be a directory junction or another error, try to remove it as a dir if unlink fails
        if os.path.isdir(target):
            try:
                os.rmdir(target)
            except OSError:
                pass

    try:
        if is_windows():
            os.symlink(source, target, target_is_directory=target_is_directory)
        else:
            os.symlink(source, target)
    except OSError as e:
        if is_windows() and getattr(e, 'winerror', 0) in (1314, 5): # ERROR_PRIVILEGE_NOT_HELD or Access Denied
            raise PermissionError(
                f"❌ Failed to create symlink at '{target}'.\n"
                "In Windows, this requires 'Developer Mode' to be enabled.\n"
                "Please enable Developer Mode: Settings -> System -> For developers -> Developer Mode.\n"
                "After enabling it, you may need to restart your terminal."
            ) from e
        raise

def find_broken_symlinks(directory):
    """Yield paths of broken symlinks in the given directory and its subdirectories."""
    if not os.path.isdir(directory):
        return
    for root, dirs, files in os.walk(directory):
        for name in list(dirs) + files:
            full_path = os.path.join(root, name)
            if os.path.islink(full_path):
                target = os.readlink(full_path)
                # Resolve relative to the link's directory
                if not os.path.isabs(target):
                    target = os.path.join(os.path.dirname(full_path), target)
                if not os.path.exists(target):
                    yield full_path

def regenerate_workspace_file(root):
    """Regenerate the mAIcelium.code-workspace file mapping linked projects."""
    projects_dir = os.path.join(root, "projects")
    
    folders = [{"path": ".", "name": "mAIcelium"}]
    
    if os.path.isdir(projects_dir):
        for entry in sorted(os.listdir(projects_dir)):
            link = os.path.join(projects_dir, entry)
            # Use os.path.exists since islink might be tricky on Win sometimes,
            # but islink is expected to work for symlinks.
            if os.path.islink(link) and os.path.isdir(link):
                real = os.path.realpath(link)
                # Convert path to posix style for VSCode workspace file to be consistent
                # but VS Code handles both.
                folders.append({"path": real, "name": entry})
                
    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    existing = {}
    if os.path.isfile(wsfile):
        try:
            with open(wsfile, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    existing["folders"] = folders
    existing.setdefault("settings", {})

    with open(wsfile, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        f.write("\n")

def get_file_content(path):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""

def regenerate_claude_context(root):
    """Regenerate .claude/projects-context.md based on rules and active projects."""
    outfile = os.path.join(root, ".claude", "projects-context.md")
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    
    lines = [
        "<!-- AUTO-GENERATED by mAIcelium scripts. Do not edit manually. -->",
        "# mAIcelium Agent Context",
        ""
    ]
    
    # Workspace rules
    lines.extend(["## Workspace Rules", ""])
    rules_dir = os.path.join(root, "mesh", "rules")
    if os.path.isdir(rules_dir):
        for rule_file in sorted(os.listdir(rules_dir)):
            if not rule_file.endswith(".md"):
                continue
            rule_path = os.path.join(rules_dir, rule_file)
            if not os.path.isfile(rule_path):
                continue
            lines.extend([f"### {os.path.splitext(rule_file)[0]}", ""])
            lines.append(get_file_content(rule_path).strip())
            lines.extend(["", ""])
            
    # Active projects
    lines.extend(["## Active Projects", ""])
    found_projects = False
    
    projects_dir = os.path.join(root, "projects")
    if os.path.isdir(projects_dir):
        for pname in sorted(os.listdir(projects_dir)):
            project_link = os.path.join(projects_dir, pname)
            if not os.path.isdir(project_link):
                continue
            found_projects = True
            
            repo_path = os.path.realpath(project_link)
            lines.extend([f"### {pname}", ""])
            
            has_rules = False
            p_rules_dir = os.path.join(repo_path, ".cursor", "rules")
            if os.path.isdir(p_rules_dir):
                for rule_file in sorted(os.listdir(p_rules_dir)):
                    rule_path = os.path.join(p_rules_dir, rule_file)
                    if not os.path.isfile(rule_path):
                        continue
                    if not has_rules:
                         lines.extend(["#### Rules", ""])
                         has_rules = True
                         
                    lines.extend([f"##### {rule_file}", ""])
                    
                    # Strip YAML frontmatter
                    content = get_file_content(rule_path)
                    content_lines = content.splitlines()
                    if content_lines and content_lines[0].strip() == "---":
                         try:
                             end_idx = content_lines.index("---", 1)
                             content_lines = content_lines[end_idx+1:]
                         except ValueError:
                             pass
                    lines.append("\n".join(content_lines).strip())
                    lines.extend(["", ""])
                    
            has_skills = False
            for skills_parent in [".cursor/skills", ".cursor/skills-cursor"]:
                 p_skills_dir = os.path.join(repo_path, *skills_parent.split('/'))
                 if not os.path.isdir(p_skills_dir):
                      continue
                 for skillname in sorted(os.listdir(p_skills_dir)):
                      skill_dir = os.path.join(p_skills_dir, skillname)
                      if not os.path.isdir(skill_dir):
                           continue
                      if not has_skills:
                           lines.extend(["#### Skills", ""])
                           has_skills = True
                      
                      # Forward slashes for markdown paths regardless of OS
                      lines.append(f"- `projects/{pname}/.cursor/skills/{skillname}/SKILL.md`")
                      
            if not has_rules and not has_skills:
                 lines.append("_No rules or skills found for this project._")
            lines.extend(["", ""])
            
    if not found_projects:
         lines.append("_No active projects._")
         
    with open(outfile, "w", encoding="utf-8") as f:
         f.write("\n".join(lines) + "\n")
