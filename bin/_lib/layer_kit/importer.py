"""Turn a repo of skills and rules, in any agent's format, into a skills repo.

Two steps, so nothing is decided behind the owner's back:
- plan(source) returns a map of every file it found: what it is, what it becomes and
  where it goes in the new repo. The map is saved as JSON for the owner to read and edit.
- apply(map, destination, ...) builds the new repo from the map, with the engine, and
  runs the trace check on the result. The source is only ever read.

Formats and how they convert (field names checked against each tool's documentation):

| Source | Becomes |
|---|---|
| A folder with SKILL.md (Agent Skills standard) | the same skill, `name:` set to its folder |
| `.cursor/rules/*.mdc` (description, globs, alwaysApply) | the same rule |
| `.claude/commands/*.md` | a skill; `description` from its frontmatter or first line |
| `.windsurf/rules/*.md` (trigger: always_on, glob, model_decision, manual; globs) | a rule: always_on is alwaysApply true, glob keeps its globs |
| `.clinerules` file or folder of .md | always-on rules |
| `.github/copilot-instructions.md` | an always-on rule |
| `.github/instructions/*.instructions.md` (applyTo) | a rule scoped to applyTo, always on for `**` |
| `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules` | one always-on rule per `## ` section; sections that read as project context are proposed as skip |
| anything else | listed as unknown and skipped |

A domain is proposed from keywords in the name, description and globs; rules without one
go to `rules/_domains/general/`, skills to `skills/_common/`.
"""

import json
import os
import re
import shutil

from . import generator

FORMAT = 1
SKIPPED_FOLDERS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
INSTRUCTION_FILES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules"}
CONTEXT_HEADINGS = re.compile(
    r"\b(overview|project|about|introduction|setup|getting started|install\w*|build\w*|commands?|"
    r"structure|architecture|repository|layout|stack|development|running)\b", re.IGNORECASE)
DOMAINS = (
    ("devops", r"terraform|ansible|docker\w*|kubernetes|k8s|helm|gcp|aws|azure|ci/cd|pipelines?|deploy\w*|infra\w*"),
    ("frontend", r"react|vue|angular|svelte|css|tsx|jsx|frontend"),
    ("backend", r"api|fastapi|django|flask|backend|graphql"),
    ("data", r"sql|database|etl|warehouse"),
)


def plan(source):
    """Map every file of source to what it becomes; reads only."""
    source = os.path.abspath(source)
    if not os.path.isdir(source):
        raise generator.LayerError("%s is not a folder" % source)
    items, claimed = [], set()
    for folder in _skill_folders(source):
        relative = _rel(folder, source)
        items.append(_skill_item(source, relative))
        claimed.add(relative + "/")
    for relative in _files(source):
        if any(relative.startswith(prefix) for prefix in claimed):
            continue
        items.append(_file_item(source, relative))
    return {"format": FORMAT, "source": source, "items": sorted(items, key=lambda entry: entry["from"])}


def apply(mapping, destination, name, owner, allow=()):
    """Build a skills repo at destination from a map made by plan()."""
    if mapping.get("format") != FORMAT:
        raise generator.LayerError("this map was not made by this version of mai kit import")
    source = mapping["source"]
    work = list(_work(mapping))
    _refuse_clashes(work)
    left_behind = [os.path.basename(entry["from"]) for entry in mapping["items"]
                   if entry["kind"] == "skill" and entry.get("action") == "skip"]

    def populate(root):
        for kind, origin, target, content in work:
            if kind == "skill":
                _copy_skill(source, origin, os.path.join(root, target))
            elif kind == "file" and target.startswith("skills/"):
                _write(os.path.join(root, target, "SKILL.md"), content)
            else:
                _write(os.path.join(root, target), content)
        return source, left_behind

    return generator.create(destination, name=name, owner=owner, allow=allow, populate=populate)


# --- plan -------------------------------------------------------------------------------

def _skill_item(source, relative):
    meta, _ = _frontmatter(_read(os.path.join(source, relative, "SKILL.md")))
    folder_name = _slug(meta.get("name") or os.path.basename(relative))
    match = re.search(r"(?:^|/)skills/(_common|_domains/[^/]+)/", relative + "/")
    if match:
        target = "skills/%s/%s" % (match.group(1), folder_name)
    else:
        domain = _domain(folder_name, meta.get("description"))
        target = "skills/%s/%s" % ("_domains/" + domain if domain else "_common", folder_name)
    return {"from": relative, "kind": "skill", "action": "copy", "to": target}


def _file_item(source, relative):
    base = os.path.basename(relative)
    text = _read(os.path.join(source, relative))
    meta, _ = _frontmatter(text) if text is not None else ({}, "")
    stem = re.sub(r"(\.instructions)?\.(mdc|md)$", "", base)
    if relative.startswith(".cursor/rules/") and base.endswith(".mdc"):
        return _rule_item(relative, "cursor-rule", "copy", stem, meta.get("description"), meta.get("globs"))
    if relative.startswith(".claude/commands/") and base.endswith(".md"):
        name = _slug(stem)
        domain = _domain(name, meta.get("description"))
        return {"from": relative, "kind": "claude-command", "action": "convert",
                "to": "skills/%s/%s" % ("_domains/" + domain if domain else "_common", name)}
    if relative.startswith(".windsurf/rules/") and base.endswith(".md"):
        return _rule_item(relative, "windsurf-rule", "convert", stem, meta.get("description"), meta.get("globs"))
    if (relative == ".clinerules" or relative.startswith(".clinerules/")) and text is not None:
        return _rule_item(relative, "cline-rule", "convert", stem if stem != ".clinerules" else "cline-rules")
    if relative == ".github/copilot-instructions.md" or (
            relative.startswith(".github/instructions/") and base.endswith(".instructions.md")):
        return _rule_item(relative, "copilot-instructions", "convert", stem, meta.get("description"),
                          meta.get("applyTo"))
    if base in INSTRUCTION_FILES and text is not None:
        return {"from": relative, "kind": "instructions-file", "action": "split",
                "sections": _sections(text, base)}
    return {"from": relative, "kind": "unknown", "action": "skip", "to": None}


def _rule_item(relative, kind, action, stem, description=None, globs=None):
    name = _slug(stem)
    domain = _domain(name, description, _join(globs)) or "general"
    return {"from": relative, "kind": kind, "action": action, "to": "rules/_domains/%s/%s.mdc" % (domain, name)}


def _sections(text, base):
    _, body = _frontmatter(text)
    parts = re.split(r"^## +(.+?)\s*$", body, flags=re.MULTILINE)
    if len(parts) == 1:
        heading = os.path.splitext(base.lstrip("."))[0]
        parts = ["", heading, body]
    sections = []
    for heading, content in zip(parts[1::2], parts[2::2]):
        name = _slug(heading)
        domain = _domain(name, heading) or "general"
        sections.append({
            "heading": heading,
            "action": "skip" if CONTEXT_HEADINGS.search(heading) else "convert",
            "to": "rules/_domains/%s/%s.mdc" % (domain, name),
        })
    return sections


# --- apply ------------------------------------------------------------------------------

def _work(mapping):
    """(kind, from, to, content) for everything the map says to write."""
    source = mapping["source"]
    for entry in mapping["items"]:
        action, kind = entry.get("action"), entry["kind"]
        if action == "skip":
            continue
        if kind == "instructions-file":
            text = _read(os.path.join(source, entry["from"]))
            bodies = _section_bodies(text, os.path.basename(entry["from"]))
            for section in entry.get("sections", []):
                if section.get("action") == "convert":
                    yield ("rule", entry["from"], _safe(section["to"]),
                           _mdc(bodies.get(section["heading"], ""), description=section["heading"], always=True))
            continue
        target = _safe(entry.get("to"))
        if kind == "skill":
            yield ("skill", entry["from"], target, None)
        else:
            yield ("file", entry["from"], target, _convert(source, entry, target))


def _convert(source, entry, target):
    text = _read(os.path.join(source, entry["from"])) or ""
    meta, body = _frontmatter(text)
    kind = entry["kind"]
    if kind == "cursor-rule":
        return text
    if kind == "claude-command":
        name = os.path.basename(target)
        description = meta.get("description") or _first_line(body) or name
        return "---\nname: %s\ndescription: %s\n---\n%s" % (name, _one_line(description), body.lstrip("\n"))
    if kind == "windsurf-rule":
        trigger = meta.get("trigger") or "always_on"
        globs = _join(meta.get("globs")) if trigger == "glob" else None
        return _mdc(body, description=meta.get("description"), globs=globs, always=trigger == "always_on")
    if kind == "cline-rule":
        return _mdc(body, always=True)
    if kind == "copilot-instructions":
        apply_to = _join(meta.get("applyTo"))
        scoped = bool(apply_to) and apply_to.strip() not in ("**", "**/*")
        return _mdc(body, description=meta.get("description"), globs=apply_to if scoped else None,
                    always=not scoped)
    raise generator.LayerError("%s: no conversion for kind %r" % (entry["from"], kind))


def _refuse_clashes(work):
    seen, names = {}, {}
    for kind, origin, target, _ in work:
        if target in seen:
            raise generator.LayerError("%s and %s both go to %s; change one of them in the map"
                                       % (seen[target], origin, target))
        seen[target] = origin
        if target.startswith("skills/"):
            name = os.path.basename(target)
            if name in names:
                raise generator.LayerError("two skills would be called %s (%s and %s); skill names must be "
                                           "unique, change one in the map" % (name, names[name], origin))
            names[name] = origin


def _copy_skill(source, origin, target):
    for relative in generator._tracked_files(source, origin):
        destination = os.path.join(target, os.path.relpath(relative, origin))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(os.path.join(source, relative), destination)
    skill_md = os.path.join(target, "SKILL.md")
    if not os.path.isfile(skill_md):
        raise generator.LayerError("%s has no tracked SKILL.md; commit it first" % origin)
    text = _read(skill_md)
    name = os.path.basename(target)
    if re.search(r"^name:", text, re.MULTILINE):
        text = re.sub(r"^name:.*$", "name: " + name, text, count=1, flags=re.MULTILINE)
    else:
        text = re.sub(r"^---\n", "---\nname: %s\n" % name, text, count=1)
    _write(skill_md, text)


def _safe(target):
    if not target or os.path.isabs(target) or ".." in target.split("/") or \
            not re.match(r"^(skills|rules)/", target):
        raise generator.LayerError("map target %r must be a path under skills/ or rules/" % target)
    return target


# --- text helpers -----------------------------------------------------------------------

def _frontmatter(text):
    """(fields, body) of a leading YAML block; a small subset: scalars and lists."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text or "", re.DOTALL)
    if not match:
        return {}, text or ""
    fields, key = {}, None
    for line in match.group(1).splitlines():
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and key:
            fields.setdefault(key, [])
            if isinstance(fields[key], list):
                fields[key].append(_unquote(item.group(1)))
            continue
        pair = re.match(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$", line)
        if pair:
            key, value = pair.group(1), pair.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                fields[key] = [_unquote(part) for part in value[1:-1].split(",") if part.strip()]
            else:
                fields[key] = _unquote(value) if value else []
    return fields, text[match.end():]


def _section_bodies(text, base):
    _, body = _frontmatter(text)
    parts = re.split(r"^## +(.+?)\s*$", body, flags=re.MULTILINE)
    if len(parts) == 1:
        return {os.path.splitext(base.lstrip("."))[0]: body}
    return {heading: content for heading, content in zip(parts[1::2], parts[2::2])}


def _mdc(body, description=None, globs=None, always=False):
    lines = ["---"]
    if description:
        lines.append("description: %s" % _one_line(description))
    if globs:
        lines.append("globs: %s" % globs)
    lines.append("alwaysApply: %s" % ("true" if always else "false"))
    lines.append("---")
    return "\n".join(lines) + "\n" + body.strip("\n") + "\n"


def _domain(*texts):
    words = " ".join(text for text in texts if isinstance(text, str)).lower()
    for domain, pattern in DOMAINS:
        if re.search(r"(?<![a-z])(%s)(?![a-z])" % pattern, words):
            return domain
    return None


def _join(value):
    if isinstance(value, list):
        return ", ".join(value) or None
    return value or None


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _first_line(body):
    return next((line.strip("# ").strip() for line in body.splitlines() if line.strip()), "")


def _one_line(text):
    return " ".join(str(text).split())


def _slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text).lower())).strip("-") or "unnamed"


def _skill_folders(source):
    found = []
    for folder, subfolders, names in os.walk(source):
        subfolders[:] = sorted(name for name in subfolders if name not in SKIPPED_FOLDERS)
        if "SKILL.md" in names:
            found.append(folder)
            subfolders[:] = []
    return found


def _files(source):
    for folder, subfolders, names in os.walk(source):
        subfolders[:] = sorted(name for name in subfolders if name not in SKIPPED_FOLDERS)
        for name in sorted(names):
            yield _rel(os.path.join(folder, name), source)


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def save(mapping, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(mapping, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise generator.LayerError("cannot read the map %s: %s" % (path, error))
