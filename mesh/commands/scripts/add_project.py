#!/usr/bin/env python3
"""Link a project into the mAIcelium workspace with fuzzy matching.

Usage: add_project.py "<user_input>"

Resolves the project name against repos/_registry.yaml entries,
then delegates to bin/add_project.sh for the actual linking.
"""
import os
import re
import subprocess
import sys

from fuzzy import fuzzy_match

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
REGISTRY = os.path.join(ROOT, "repos", "_registry.yaml")


def load_registry():
    """Load the registry and return a dict of {name: path}.

    Parses the YAML without external dependencies by extracting
    name/path pairs from the known structure.
    """
    if not os.path.isfile(REGISTRY):
        return {}

    with open(REGISTRY) as f:
        content = f.read()

    entries = {}
    current_category = None
    current_name = None
    current_repos_section = False
    current_repo_name = None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level category (no indentation)
        if re.match(r"^[a-zA-Z_-]+:\s*$", line):
            current_category = stripped.rstrip(":")
            current_name = None
            current_repos_section = False
            continue

        # Second-level entry (2-space indent)
        m = re.match(r"^  ([a-zA-Z0-9_-]+):\s*(.*)?$", line)
        if m:
            current_name = m.group(1)
            current_repos_section = False
            current_repo_name = None
            rest = (m.group(2) or "").strip()
            # Inline dict: {path: ~/dev/foo, tech: [...]}
            pm = re.search(r"path:\s*([^\s,}]+)", rest)
            if pm:
                entries[current_name] = os.path.expanduser(pm.group(1))
            continue

        # Check for "repos:" under a named entry
        if re.match(r"^    repos:\s*$", line):
            current_repos_section = True
            continue

        # Check for "path:" at 4-space indent (direct path under entry)
        pm = re.match(r"^    path:\s*(.+)$", line)
        if pm and current_name and not current_repos_section:
            entries[current_name] = os.path.expanduser(pm.group(1).strip())
            continue

        # Sub-repo name under "repos:" (6-space indent)
        m = re.match(r"^      ([a-zA-Z0-9_-]+):\s*(.*)?$", line)
        if m and current_repos_section and current_name:
            current_repo_name = m.group(1)
            rest = (m.group(2) or "").strip()
            pm = re.search(r"path:\s*([^\s,}]+)", rest)
            if pm:
                key = current_name if current_repo_name == "main" else f"{current_name}-{current_repo_name}"
                entries[key] = os.path.expanduser(pm.group(1))
            continue

        # Path under a sub-repo (8-space indent)
        pm = re.match(r"^        path:\s*(.+)$", line)
        if pm and current_repos_section and current_name and current_repo_name:
            key = current_name if current_repo_name == "main" else f"{current_name}-{current_repo_name}"
            entries[key] = os.path.expanduser(pm.group(1).strip())
            continue

    return entries


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("❌ No project name provided.")
        print("Usage: /add_project <name>")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:]).strip()
    registry = load_registry()

    if not registry:
        print("❌ Registry is empty. Check repos/_registry.yaml")
        sys.exit(1)

    available = sorted(registry.keys())
    match, candidates = fuzzy_match(user_input, available)

    if not match and candidates:
        names = ", ".join(f"**{c}**" for c in candidates)
        print(f"❓ **{user_input}** is ambiguous: {names}")
        print("Please specify which one you meant.")
        sys.exit(2)

    if not match:
        print(f"❌ **{user_input}** not found in registry.")
        print(f"Available: {', '.join(available)}")
        sys.exit(1)

    repo_path = registry[match]

    if not os.path.isdir(repo_path):
        print(f"❌ Path does not exist: {repo_path}")
        sys.exit(1)

    # Check if already linked
    link = os.path.join(ROOT, "projects", match)
    if os.path.islink(link):
        print(f"⚠️ **{match}** is already linked.")
        sys.exit(0)

    # Delegate to the Python script
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "bin", "add_project.py"), match, repo_path],
        capture_output=False,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
