"""Generators for workspace files: mAIcelium.code-workspace and .claude/projects-context.md.

Ports two bash helpers from bin/_lib.sh:
- _regenerate_workspace_file (lines 139-174)
- _regenerate_claude_context  (lines 235-383)
"""
import glob
import json
import os
import re

from _lib.conventions import load_conventions
from _lib.workspace import load_workspace_section


_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def _strip_frontmatter(content):
    """Remove a leading YAML frontmatter block (``---\\n...\\n---\\n``) if present."""
    return _FRONTMATTER_RE.sub("", content, count=1)


def _read_text(path):
    """Read a file as text; return empty string on failure."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def regenerate_workspace_file(root):
    """Regenerate mAIcelium.code-workspace from the projects/ symlinks.

    Builds a folders list from sorted symlink-to-dir entries under projects/,
    preserves any existing settings, and writes JSON with indent=2.
    """
    projects_dir = os.path.join(root, "projects")

    folders = [{"path": ".", "name": "mAIcelium"}]

    if os.path.isdir(projects_dir):
        for entry in sorted(os.listdir(projects_dir)):
            link = os.path.join(projects_dir, entry)
            if os.path.islink(link) and os.path.isdir(link):
                real = os.path.realpath(link)
                folders.append({"path": real, "name": entry})

    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    existing = {}
    if os.path.isfile(wsfile):
        try:
            with open(wsfile, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["folders"] = folders
    existing.setdefault("settings", {})

    with open(wsfile, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _layer_dirs_for(mesh_layers, pname):
    """Return (rules_dir, skills_dir) of the mesh layer whose client == pname.

    Either may be empty string if no layer matches or layer has no path.
    """
    for layer in mesh_layers:
        if layer.get("client") == pname:
            p = layer.get("path", "")
            if not p:
                return "", ""
            return os.path.join(p, "rules"), os.path.join(p, "skills")
    return "", ""


def _emit_project(out, pname, repo_path, conventions, mesh_layers, no_inline):
    """Append the section for one project to the out list."""
    out.append(f"### {pname}\n")
    out.append("\n")

    if pname in no_inline:
        out.append(
            "_Framework repo — rules and skills not inlined to avoid duplication. "
            "Content available via mesh layers._\n"
        )
        out.append("\n")
        return

    layer_rules_dir, layer_skills_dir = _layer_dirs_for(mesh_layers, pname)

    data_dir = conventions["project_data_dir"]
    rules_subdir = conventions["project_rules_subdir"]
    skills_subdirs = conventions["project_skills_subdirs"]
    data_subdirs = conventions["project_data_subdirs"]

    # ── Rules: project-native + mesh layer ───────────────────────────────────
    has_rules = False
    rules_dirs = [os.path.join(repo_path, data_dir, rules_subdir)]
    if layer_rules_dir:
        rules_dirs.append(layer_rules_dir)

    for rdir in rules_dirs:
        if not rdir or not os.path.isdir(rdir):
            continue
        for rule in sorted(os.listdir(rdir)):
            rule_path = os.path.join(rdir, rule)
            if not os.path.isfile(rule_path):
                continue
            if not has_rules:
                out.append("#### Rules\n")
                out.append("\n")
                has_rules = True
            out.append(f"##### {rule}\n")
            out.append("\n")
            out.append(_strip_frontmatter(_read_text(rule_path)))
            out.append("\n")

    # ── Skills: project-native + mesh layer ──────────────────────────────────
    has_skills = False
    skills_dirs = [os.path.join(repo_path, data_dir, s) for s in skills_subdirs]
    if layer_skills_dir:
        skills_dirs.append(layer_skills_dir)

    for sdir in skills_dirs:
        if not sdir or not os.path.isdir(sdir):
            continue
        for skill_name in sorted(os.listdir(sdir)):
            skill_dir = os.path.join(sdir, skill_name)
            if not os.path.isdir(skill_dir):
                continue
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_file):
                continue
            if not has_skills:
                out.append("#### Skills\n")
                out.append("\n")
                has_skills = True
            out.append(f"##### {skill_name}\n")
            out.append("\n")
            out.append(_strip_frontmatter(_read_text(skill_file)))
            out.append("\n")

    # ── Project data directories ─────────────────────────────────────────────
    has_data = False
    for d in data_subdirs:
        full = os.path.join(repo_path, data_dir, d)
        if not os.path.isdir(full):
            continue
        if not has_data:
            out.append("#### Project Data (accessible via symlink)\n")
            out.append("\n")
            has_data = True
        out.append(f"- `projects/{pname}/{data_dir}/{d}/`\n")
    if has_data:
        out.append("\n")

    if not has_rules and not has_skills:
        out.append("_No rules or skills found for this project._\n")
    out.append("\n")


def regenerate_claude_context(root):
    """Regenerate .claude/projects-context.md from mesh/ and projects/.

    Writes a markdown file with workspace rules (from mesh/rules/*.mdc) and
    per-project sections containing inlined rules, skills, and a project-data
    index. Mirrors _regenerate_claude_context from bin/_lib.sh.
    """
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    outfile = os.path.join(claude_dir, "projects-context.md")

    conventions = load_conventions(root)
    mesh_layers = load_workspace_section(root, "mesh_layers")
    no_inline = load_workspace_section(root, "no_inline_projects")

    out = []
    out.append("<!-- AUTO-GENERATED by mAIcelium scripts. Do not edit manually. -->\n")
    out.append("# mAIcelium Agent Context\n")
    out.append("\n")

    # ── Workspace rules (mesh/rules/*.mdc) ────────────────────────────────────
    out.append("## Workspace Rules\n")
    out.append("\n")
    mesh_rules_glob = os.path.join(root, "mesh", "rules", "*.mdc")
    for rule_path in sorted(glob.glob(mesh_rules_glob)):
        if not os.path.isfile(rule_path):
            continue
        name = os.path.basename(rule_path)[: -len(".mdc")]
        out.append(f"### {name}\n")
        out.append("\n")
        out.append(_strip_frontmatter(_read_text(rule_path)))
        out.append("\n")

    # ── Active projects ──────────────────────────────────────────────────────
    out.append("## Active Projects\n")
    out.append("\n")

    projects_dir = os.path.join(root, "projects")
    found_projects = False

    if os.path.isdir(projects_dir):
        for entry in sorted(os.listdir(projects_dir)):
            link = os.path.join(projects_dir, entry)
            if not os.path.isdir(link):
                continue
            found_projects = True
            repo_path = os.path.realpath(link)
            _emit_project(out, entry, repo_path, conventions, mesh_layers, no_inline)

    if not found_projects:
        out.append("_No active projects._\n")

    with open(outfile, "w", encoding="utf-8") as f:
        f.write("".join(out))
