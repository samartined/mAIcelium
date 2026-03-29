#!/usr/bin/env python3
"""Run health checks across all linked projects and workspace.

Usage: project_health.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
PROJECTS_DIR = os.path.join(ROOT, "projects")
CURSOR_RULES = os.path.join(ROOT, ".cursor", "rules")
CURSOR_SKILLS = os.path.join(ROOT, ".cursor", "skills-cursor")
SKILLS_COMMON = os.path.join(ROOT, "mesh", "skills", "_common")
SKILLS_DOMAINS = os.path.join(ROOT, "mesh", "skills", "_domains")
SKIP = {".gitkeep"}


def run_git(repo_path, *args):
    """Run a git command in a repo and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_project(name, link_path):
    """Check a single project's health. Returns (status_emoji, details)."""
    target = os.path.realpath(link_path)
    issues = []

    if not os.path.isdir(target):
        return "❌", f"Broken symlink → {target}"

    # Git status
    branch = run_git(target, "rev-parse", "--abbrev-ref", "HEAD")
    status = run_git(target, "status", "--porcelain")

    if branch:
        dirty = " (dirty)" if status else " (clean)"
        details_branch = f"branch: `{branch}`{dirty}"
    else:
        details_branch = "no git repo"
        issues.append("not a git repository")

    # Check ahead/behind remote
    ahead_behind = ""
    if branch:
        tracking = run_git(target, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}")
        if tracking:
            ab = run_git(target, "rev-list", "--left-right", "--count", f"{tracking}...HEAD")
            if ab:
                parts = ab.split()
                behind, ahead = int(parts[0]), int(parts[1])
                if ahead > 0:
                    ahead_behind += f" ↑{ahead}"
                if behind > 0:
                    ahead_behind += f" ↓{behind}"
                    issues.append(f"{behind} commits behind remote")

    # README check
    has_readme = os.path.isfile(os.path.join(target, "README.md"))
    if not has_readme:
        issues.append("no README.md")

    # .env in git check
    gitignore = os.path.join(target, ".gitignore")
    env_file = os.path.join(target, ".env")
    if os.path.isfile(env_file):
        env_ignored = False
        if os.path.isfile(gitignore):
            with open(gitignore) as f:
                if ".env" in f.read():
                    env_ignored = True
        if not env_ignored:
            issues.append(".env exists but may not be gitignored")

    emoji = "✅" if not issues else "⚠️"
    detail = f"{details_branch}{ahead_behind}"
    if issues:
        detail += f" — {', '.join(issues)}"

    return emoji, detail


def check_workspace_symlinks():
    """Check for broken symlinks in .cursor/ directories."""
    broken = []
    for dir_path in [CURSOR_RULES, CURSOR_SKILLS]:
        if not os.path.isdir(dir_path):
            continue
        for entry in os.listdir(dir_path):
            full = os.path.join(dir_path, entry)
            if os.path.islink(full) and not os.path.exists(full):
                broken.append(os.path.relpath(full, ROOT))
    return broken


def count_skills():
    """Count skills with SKILL.md vs placeholder directories."""
    complete = 0
    placeholder = 0

    for base in [SKILLS_COMMON, SKILLS_DOMAINS]:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            if entry in SKIP or entry.startswith("."):
                continue
            entry_path = os.path.join(base, entry)
            if not os.path.isdir(entry_path):
                continue
            # Check if SKILL.md exists directly or in subdirectories
            if os.path.isfile(os.path.join(entry_path, "SKILL.md")):
                complete += 1
            else:
                # Check nested (e.g., _domains/obsidian/json-canvas/SKILL.md)
                has_skill = False
                for sub in os.listdir(entry_path):
                    sub_path = os.path.join(entry_path, sub)
                    if os.path.isdir(sub_path) and os.path.isfile(
                        os.path.join(sub_path, "SKILL.md")
                    ):
                        has_skill = True
                        complete += 1
                if not has_skill and not any(
                    os.path.isfile(os.path.join(entry_path, sub, "SKILL.md"))
                    for sub in os.listdir(entry_path)
                    if os.path.isdir(os.path.join(entry_path, sub))
                ):
                    placeholder += 1

    return complete, placeholder


def main():
    print("# Project Health Report\n")

    # ── Projects ─────────────────────────────────────────────────────────────
    if not os.path.isdir(PROJECTS_DIR):
        print("📭 No projects directory found.\n")
    else:
        projects = sorted(
            e
            for e in os.listdir(PROJECTS_DIR)
            if os.path.islink(os.path.join(PROJECTS_DIR, e)) and e not in SKIP
        )

        if not projects:
            print("📭 No projects linked.\n")
        else:
            print(f"## Projects ({len(projects)})\n")
            for name in projects:
                link_path = os.path.join(PROJECTS_DIR, name)
                emoji, detail = check_project(name, link_path)
                print(f"  {emoji} **{name}** — {detail}")
            print()

    # ── Workspace symlinks ───────────────────────────────────────────────────
    print("## Workspace Integrity\n")
    broken = check_workspace_symlinks()
    if broken:
        print(f"  ⚠️  {len(broken)} broken symlink(s):")
        for b in broken:
            print(f"    • {b}")
    else:
        print("  ✅ All symlinks valid.")

    # ── Skills status ────────────────────────────────────────────────────────
    complete, placeholder = count_skills()
    total = complete + placeholder
    print(f"\n  📦 Skills: {complete}/{total} complete", end="")
    if placeholder > 0:
        print(f" ({placeholder} placeholder(s))")
    else:
        print(" — all complete")

    # ── Overall ──────────────────────────────────────────────────────────────
    all_ok = not broken and placeholder == 0
    print(f"\n{'✅' if all_ok else '⚠️'} Health check complete.")


if __name__ == "__main__":
    main()
