#!/usr/bin/env python3
"""Run health checks across all linked projects and workspace.

Usage: project_health.py
"""
import os
import subprocess
import sys

SKIP = {".gitkeep"}


def _get_root():
    """Resolve workspace root. Allow override via MAICELIUM_ROOT for tests."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    # mesh/commands/scripts/project_health.py -> root is 4 levels up from this file
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def _safe_stdout():
    """Reconfigure stdout to survive cp1252/latin-1 consoles without crashing."""
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


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
            with open(gitignore, encoding="utf-8") as f:
                if ".env" in f.read():
                    env_ignored = True
        if not env_ignored:
            issues.append(".env exists but may not be gitignored")

    emoji = "✅" if not issues else "⚠️"
    detail = f"{details_branch}{ahead_behind}"
    if issues:
        detail += f" — {', '.join(issues)}"

    return emoji, detail


def check_workspace_symlinks(root):
    """Check for broken symlinks in .cursor/ directories."""
    cursor_rules = os.path.join(root, ".cursor", "rules")
    cursor_skills = os.path.join(root, ".cursor", "skills-cursor")
    broken = []
    for dir_path in [cursor_rules, cursor_skills]:
        if not os.path.isdir(dir_path):
            continue
        for entry in os.listdir(dir_path):
            full = os.path.join(dir_path, entry)
            if os.path.islink(full) and not os.path.exists(full):
                broken.append(os.path.relpath(full, root))
    return broken


def count_skills(root):
    """Count skills with SKILL.md vs placeholder directories."""
    skills_common = os.path.join(root, "mesh", "skills", "_common")
    skills_domains = os.path.join(root, "mesh", "skills", "_domains")
    complete = 0
    placeholder = 0

    for base in [skills_common, skills_domains]:
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
    """Run health checks and return an exit code.

    Returns:
        0 -- healthy or issues found (warnings, placeholder skills, no-git, no-README)
        2 -- broken project symlinks detected (a project/ entry points at a non-existent target)

    D1 override: main() now computes and returns an int instead of returning None.
    __main__ calls sys.exit(main()) so the process exits with the correct code.
    The '1 = issues' tier from the original D1 parenthetical was deliberately dropped:
    D1 also mandates 'The 4 existing healthy-case project_health tests stay exit 0', and
    those tests cover projects with real issues (no git, no README) that must stay 0.
    Only broken project symlinks (projects/ entries with non-existent targets) trigger 2.
    Workspace-level warnings (broken .cursor symlinks, placeholder skills) stay 0.
    The existing report TEXT (header, 'Broken symlink' line) is preserved.
    """
    _safe_stdout()
    root = _get_root()
    projects_dir = os.path.join(root, "projects")

    print("# Project Health Report\n")

    has_broken = False

    # ── Projects ─────────────────────────────────────────────────────────────
    if not os.path.isdir(projects_dir):
        print("📭 No projects directory found.\n")
    else:
        projects = sorted(
            e
            for e in os.listdir(projects_dir)
            if os.path.islink(os.path.join(projects_dir, e)) and e not in SKIP
        )

        if not projects:
            print("📭 No projects linked.\n")
        else:
            print(f"## Projects ({len(projects)})\n")
            for name in projects:
                link_path = os.path.join(projects_dir, name)
                emoji, detail = check_project(name, link_path)
                print(f"  {emoji} **{name}** — {detail}")
                if emoji == "❌":
                    has_broken = True
            print()

    # ── Workspace symlinks ───────────────────────────────────────────────────
    print("## Workspace Integrity\n")
    broken = check_workspace_symlinks(root)
    if broken:
        print(f"  ⚠️  {len(broken)} broken symlink(s):")
        for b in broken:
            print(f"    • {b}")
    else:
        print("  ✅ All symlinks valid.")

    # ── Skills status ────────────────────────────────────────────────────────
    complete, placeholder = count_skills(root)
    total = complete + placeholder
    print(f"\n  📦 Skills: {complete}/{total} complete", end="")
    if placeholder > 0:
        print(f" ({placeholder} placeholder(s))")
    else:
        print(" — all complete")

    # ── Overall ──────────────────────────────────────────────────────────────
    all_ok = not broken and placeholder == 0 and not has_broken
    print(f"\n{'✅' if all_ok else '⚠️'} Health check complete.")

    # Return exit code: 2=broken project symlinks, 0=healthy/issues
    # D1 override: main() now returns an int; only broken project symlinks
    # (projects/ entries pointing at non-existent targets) cause exit 2.
    # Workspace-level warnings (placeholder skills, broken .cursor symlinks)
    # and project-level issues (no git, no README) keep exit 0 per the spec:
    # "The 4 existing healthy-case project_health tests stay exit 0."
    if has_broken:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
