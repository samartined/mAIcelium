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

# Matches an explicit `alwaysApply: false` line inside a frontmatter block.
# MULTILINE so ^ anchors to each line.  We scan ONLY the isolated frontmatter
# block, never the rule body, to avoid false matches in prose.
_ALWAYS_APPLY_FALSE_RE = re.compile(
    r"^\s*alwaysApply\s*:\s*false\s*$", re.MULTILINE
)

# Frontmatter keys Claude Code requires to register a skill found under
# .claude/skills/<name>/SKILL.md. Matched inside the frontmatter block only.
_SKILL_NAME_RE = re.compile(r"^\s*name\s*:", re.MULTILINE)
_SKILL_DESCRIPTION_RE = re.compile(r"^\s*description\s*:", re.MULTILINE)


def _is_opt_out(content):
    """Return True only when frontmatter explicitly sets ``alwaysApply: false``.

    No frontmatter, missing key, malformed, or ``alwaysApply: true`` → False
    (include by default — opt-out semantics).  Scans the frontmatter block
    only so body prose containing "alwaysApply: false" never triggers exclusion.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return False  # no frontmatter → include
    frontmatter_block = m.group(0)
    return bool(_ALWAYS_APPLY_FALSE_RE.search(frontmatter_block))


def _strip_frontmatter(content):
    """Remove a leading YAML frontmatter block (``---\\n...\\n---\\n``) if present."""
    return _FRONTMATTER_RE.sub("", content, count=1)


def _is_natively_registrable(content):
    """True if a SKILL.md carries frontmatter with both ``name:`` and ``description:``.

    Claude Code registers a skill from ``.claude/skills/<name>/SKILL.md`` only
    when both keys are present; anything else is ignored silently. Scans the
    isolated frontmatter block, never the body, so prose cannot produce a false
    positive. Callers use this to decide whether the body still needs inlining:
    a registrable skill is reachable on demand, an unregistrable one is not.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return False
    block = m.group(0)
    return bool(
        _SKILL_NAME_RE.search(block) and _SKILL_DESCRIPTION_RE.search(block)
    )


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
    # sync_symlinks.py reflects these same skills into .claude/skills/, where
    # Claude Code registers them and loads each SKILL.md on demand. Inlining
    # their full bodies here as well would duplicate every skill in the context
    # file — the KI-001 failure mode that pushed it to 204KB. So a registrable
    # skill gets an index entry only.
    #
    # A skill WITHOUT usable frontmatter never registers natively, and dropping
    # its body would make it invisible in Claude Code instead of merely
    # duplicated. Those keep being inlined in full.
    registered = []
    unregistered = []
    seen = set()

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
            # First source wins, matching the reflection planner's
            # skip-if-link-exists behaviour for duplicate skill names.
            if skill_name in seen:
                continue
            seen.add(skill_name)
            content = _read_text(skill_file)
            if _is_natively_registrable(content):
                registered.append(skill_name)
            else:
                unregistered.append((skill_name, content))

    has_skills = bool(registered or unregistered)
    if has_skills:
        out.append("#### Skills\n")
        out.append("\n")

    if registered:
        out.append(
            f"Registered natively under `.claude/skills/` as `{pname}--<skill>`. "
            "Claude Code loads each one on demand, so the bodies are not "
            "inlined here:\n"
        )
        out.append("\n")
        for skill_name in registered:
            out.append(f"- `{pname}--{skill_name}`\n")
        out.append("\n")

    if unregistered:
        out.append(
            "_Inlined below because they lack the frontmatter (`name` + "
            "`description`) Claude Code needs to register them natively:_\n"
        )
        out.append("\n")
        for skill_name, content in unregistered:
            out.append(f"##### {skill_name}\n")
            out.append("\n")
            out.append(_strip_frontmatter(content))
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


_INDEX_START = "<!-- READING-INDEX:START -->"
_INDEX_END = "<!-- READING-INDEX:END -->"

_PREAMBLE = [
    "<!-- AUTO-GENERATED by mAIcelium scripts. Do not edit manually. -->\n",
    "# mAIcelium Agent Context\n",
    "\n",
]


def _count_lines(parts):
    return sum(part.count("\n") for part in parts)


def _render_reading_index(sections, body_lines, offset):
    """Render the navigation table that prefaces projects-context.md.

    ``sections`` is a list of ``(title, tier)`` paired with a body-relative
    start line; ``offset`` is how many lines the preamble plus this index
    occupy, so the printed ranges address the final file rather than the body.

    Row count depends only on ``len(sections)``, so the rendered height is
    identical for any offset. That lets the caller measure with ``offset=0``
    and re-render once with the real value — see ``regenerate_claude_context``.
    """
    total = body_lines + offset
    lines = [
        _INDEX_START + "\n",
        f"> **Do not read this file whole — it is {total} lines.**\n",
        "> Read every `always` row before starting work. Read an `on-demand`\n",
        "> row only when the task touches it, addressing it by the line range\n",
        "> below (`Read` with `offset` and `limit`). Ranges are regenerated with\n",
        "> the content, so they cannot go stale.\n",
        "\n",
        "| Lines | Tier | Section |\n",
        "|---|---|---|\n",
    ]
    for i, (title, tier, start) in enumerate(sections):
        end = sections[i + 1][2] - 1 if i + 1 < len(sections) else body_lines
        label = "**always**" if tier == "always" else "on-demand"
        lines.append(f"| {start + offset}-{end + offset} | {label} | {title} |\n")
    lines.append(_INDEX_END + "\n")
    lines.append("\n")
    return lines


def regenerate_claude_context(root):
    """Regenerate .claude/projects-context.md from mesh/ and projects/.

    Writes a markdown file with workspace rules (from mesh/rules/*.mdc) and
    per-project sections containing inlined rules, a skills index, and a
    project-data index. Mirrors _regenerate_claude_context from bin/_lib.sh,
    except that skill bodies are no longer inlined when the skill registers
    natively under .claude/skills/ (see _emit_project).

    The file opens with a generated reading index giving every section's line
    range and tier, so a reader can load the always-on rules and the one
    active project instead of the whole file. Rules reach here only when they
    are always-on already: ``alwaysApply: false`` excludes a domain rule
    upstream in ``_is_opt_out``, so the per-project sections carry the
    on-demand tier.
    """
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    outfile = os.path.join(claude_dir, "projects-context.md")

    conventions = load_conventions(root)
    mesh_layers = load_workspace_section(root, "mesh_layers")
    no_inline = load_workspace_section(root, "no_inline_projects")

    out = []
    sections = []

    def open_section(title, tier):
        sections.append((title, tier, _count_lines(out) + 1))

    # ── Workspace rules (mesh/rules/*.mdc) ────────────────────────────────────
    open_section("Workspace Rules", "always")
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

    # ── Domain Rules (mesh/rules/_domains/<domain>/*.mdc) ────────────────────
    # Rules in _domains/ are opt-out by default: a rule is inlined UNLESS its
    # frontmatter explicitly sets `alwaysApply: false`.
    # Sorted deterministically: domain dir first, then filename.
    # The `seen` set (by realpath inode) guards against a flat-tier symlink and
    # a _domains/ file resolving to the same physical file.  It does NOT protect
    # against two distinct files that share the same <domain>/<rule> heading
    # name — callers must avoid shipping duplicate-named files across layers.
    domains_dir = os.path.join(root, "mesh", "rules", "_domains")
    domain_rules_out = []
    if os.path.isdir(domains_dir):
        seen_domain = set()
        for domain in sorted(os.listdir(domains_dir)):
            domain_path = os.path.join(domains_dir, domain)
            if not os.path.isdir(domain_path):
                continue
            for fname in sorted(os.listdir(domain_path)):
                if not fname.endswith(".mdc"):
                    continue
                rule_path = os.path.join(domain_path, fname)
                if not os.path.isfile(rule_path):
                    continue
                real = os.path.realpath(rule_path)
                if real in seen_domain:
                    continue
                seen_domain.add(real)
                content = _read_text(rule_path)
                if _is_opt_out(content):
                    continue
                rule_name = fname[: -len(".mdc")]
                domain_rules_out.append(f"### {domain}/{rule_name}\n")
                domain_rules_out.append("\n")
                domain_rules_out.append(_strip_frontmatter(content))
                domain_rules_out.append("\n")

    if domain_rules_out:
        open_section("Domain Rules", "always")
        out.append("## Domain Rules\n")
        out.append("\n")
        out.extend(domain_rules_out)

    # ── Active projects ──────────────────────────────────────────────────────
    open_section("Active Projects", "on-demand")
    out.append("## Active Projects\n")
    out.append("\n")

    projects_dir = os.path.join(root, "projects")
    found_projects = False

    if os.path.isdir(projects_dir):
        for entry in sorted(os.listdir(projects_dir)):
            link = os.path.join(projects_dir, entry)
            if not os.path.isdir(link):
                continue
            open_section(f"Project: {entry}", "on-demand")
            found_projects = True
            repo_path = os.path.realpath(link)
            _emit_project(out, entry, repo_path, conventions, mesh_layers, no_inline)

    if not found_projects:
        out.append("_No active projects._\n")

    body_lines = _count_lines(out)
    probe = _render_reading_index(sections, body_lines, 0)
    offset = len(_PREAMBLE) + len(probe)
    index = _render_reading_index(sections, body_lines, offset)

    with open(outfile, "w", encoding="utf-8") as f:
        f.write("".join(_PREAMBLE + index + out))
