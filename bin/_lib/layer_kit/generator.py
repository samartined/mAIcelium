"""Build a new skills repo from the layer kit.

The result has the mAIcelium layer layout (skills/_common, skills/_domains,
rules/_domains), so a workspace can mount it, and the engine in claude/, so any Claude
Code session on a machine where its owner ran `claude/doctor.py --fix` sees its skills
and runs its hooks. The engine files are copied byte for byte; everything that names the
repo is written from the arguments.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

from . import leaks

KIT = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(KIT, "engine")
SKELETON = os.path.join(KIT, "skeleton")
ENGINE_HOOKS = os.path.join("hooks", "engine-hooks.json")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
TEMPLATED = ("README.md", "AGENTS.md", os.path.join("claude", "hard-rules.md"))
RENAMED = {"gitignore": ".gitignore"}


class LayerError(Exception):
    """A request the kit refuses; the message says why and what to do."""


def create(destination, name, owner, with_skills=(), with_rules=(), allow=(), populate=None):
    """Write a new skills repo at destination.

    with_skills: skill folders of another repo to start with. Each brings its hooks (from
    that repo's claude/hooks/registry.json), the hooks those need and the skills they
    serve. with_rules: rule files of the same repo. Both keep their place in the layout.
    Returns {"path", "skills", "rules", "hooks", "added"}, where "added" lists the skills
    pulled in by hooks rather than asked for.

    populate: an optional step that adds content to the new repo before it is checked
    for traces; it is called with the staging folder and returns (source, names of the
    source's skills that were left behind).
    """
    if not SLUG.match(name or ""):
        raise LayerError("the plugin name must be lowercase letters, digits and dashes: %r" % name)
    if not (owner or "").strip():
        raise LayerError("the owner's name is required")
    destination = os.path.abspath(destination)
    if os.path.exists(destination) and (not os.path.isdir(destination) or os.listdir(destination)):
        raise LayerError("%s already exists and is not empty; choose another folder" % destination)
    selection = _select(with_skills, with_rules)
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".kit-", dir=parent)
    try:
        _write_skeleton(staging, name, owner)
        _write_engine(staging)
        _write_identity(staging, name, owner)
        if selection:
            _copy_selection(staging, selection)
            left_behind = (leaks.left_behind_skills(selection["source"], sorted(selection["skills"]))
                           + leaks.left_behind_rules(selection["source"], sorted(selection["rules"])))
            refuse_traces(staging, selection["source"], left_behind, keep=[owner, *allow])
        if populate:
            source, left_behind = populate(staging)
            refuse_traces(staging, source, left_behind, keep=[owner, *allow])
        _git_init(staging)
        if os.path.isdir(destination):
            os.rmdir(destination)
        os.rename(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "path": destination,
        "skills": sorted(selection["skills"]) if selection else [],
        "hooks": sorted(selection["hooks"]) if selection else [],
        "added": sorted(selection["skills"] - selection["asked"]) if selection else [],
        "rules": sorted(selection["rules"]) if selection else [],
    }


def engine_files():
    """Paths of the engine files, relative to claude/."""
    found = []
    for folder, subfolders, names in os.walk(ENGINE):
        subfolders[:] = sorted(name for name in subfolders if name != "__pycache__")
        for name in sorted(names):
            if not name.endswith(".pyc"):
                found.append(os.path.relpath(os.path.join(folder, name), ENGINE))
    return found


def _write_skeleton(root, name, owner):
    for folder, subfolders, names in os.walk(SKELETON):
        subfolders[:] = [entry for entry in subfolders if entry != "__pycache__"]
        relative_folder = os.path.relpath(folder, SKELETON)
        os.makedirs(os.path.join(root, relative_folder), exist_ok=True)
        for file_name in names:
            relative = os.path.normpath(os.path.join(relative_folder, RENAMED.get(file_name, file_name)))
            source = os.path.join(folder, file_name)
            target = os.path.join(root, relative)
            if relative in TEMPLATED:
                with open(source, encoding="utf-8") as handle:
                    text = handle.read().replace("{{name}}", name).replace("{{owner}}", owner)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(text)
            else:
                shutil.copyfile(source, target)


def _write_engine(root):
    hashes = {}
    for relative in engine_files():
        target = os.path.join(root, "claude", relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ENGINE, relative), target)
        hashes[relative.replace(os.sep, "/")] = _sha256(target)
    _write_json(os.path.join(root, "claude", "engine.json"), {
        "source": "mAIcelium layer kit",
        "files": hashes,
    })


def _write_identity(root, name, owner):
    claude = os.path.join(root, "claude")
    _write_json(os.path.join(claude, ".claude-plugin", "plugin.json"), {
        "name": name,
        "version": "0.1.0",
        "description": "Hooks of the %s skills repo, delivered to every Claude Code session. Holds no "
                       "skills: those are personal links kept in sync by the SessionStart hook." % name,
        "author": {"name": owner},
    })
    with open(os.path.join(ENGINE, ENGINE_HOOKS), encoding="utf-8") as handle:
        engine_hooks = json.load(handle)
    _write_json(os.path.join(claude, "hooks", "registry.json"), engine_hooks["registry"])
    _write_json(os.path.join(claude, "hooks", "hooks.json"), {"hooks": engine_hooks["hooks"]})


def _git_init(root):
    completed = subprocess.run(["git", "init", "-q", "-b", "main", root], capture_output=True, text=True)
    if completed.returncode != 0:
        raise LayerError("git init failed: %s" % completed.stderr.strip())


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def select(source, only=()):
    """Skill folders and rule files of source to share: everything, or what `only` names.

    Each name in `only` is `_common`, a domain (its skills and its rules), a skill folder
    name or a rule name (with or without .mdc).
    """
    source = os.path.realpath(source)
    skills_root, rules_root = os.path.join(source, "skills"), os.path.join(source, "rules")
    if not os.path.isdir(skills_root) and not os.path.isdir(rules_root):
        raise LayerError("%s has no skills/ or rules/ folder" % source)
    all_skills = [folder for folder, _, names in os.walk(skills_root) if "SKILL.md" in names]
    all_rules = [os.path.join(folder, name) for folder, _, names in os.walk(rules_root)
                 for name in names if name.endswith(".mdc")]
    if not only:
        return sorted(all_skills), sorted(all_rules)
    skills, rules = set(), set()
    for name in only:
        name = name.strip().strip("/")
        if name == "_common":
            areas = [os.path.join(skills_root, "_common"), os.path.join(rules_root, "_common")]
        else:
            areas = [os.path.join(skills_root, "_domains", name), os.path.join(rules_root, "_domains", name)]
        picked_skills = [path for path in all_skills if any(_within(path, area) for area in areas)]
        picked_rules = [path for path in all_rules if any(_within(path, area) for area in areas)]
        if not picked_skills and not picked_rules:
            stem = name[:-4] if name.endswith(".mdc") else name
            picked_skills = [path for path in all_skills if os.path.basename(path) == name]
            picked_rules = [path for path in all_rules if os.path.basename(path) == stem + ".mdc"]
        if not picked_skills and not picked_rules:
            raise LayerError("%s has no domain, skill or rule called %s" % (source, name))
        skills.update(picked_skills)
        rules.update(picked_rules)
    return sorted(skills), sorted(rules)


def _within(path, folder):
    return path == folder or path.startswith(folder + os.sep)


def _select(with_skills, with_rules=()):
    """Work out which skills, rules and hooks to copy from the source repo."""
    if not with_skills and not with_rules:
        return None
    sources, asked, asked_rules = set(), set(), set()
    for folder in with_skills:
        folder = os.path.realpath(folder)
        if not os.path.isfile(os.path.join(folder, "SKILL.md")):
            raise LayerError("%s is not a skill folder: it has no SKILL.md" % folder)
        source = _source_root(folder)
        sources.add(source)
        asked.add(os.path.relpath(folder, os.path.join(source, "skills")).replace(os.sep, "/"))
    for path in with_rules:
        path = os.path.realpath(path)
        if not (path.endswith(".mdc") and os.path.isfile(path)):
            raise LayerError("%s is not a rule file (.mdc)" % path)
        source = _source_root(path, "rules")
        sources.add(source)
        asked_rules.add(os.path.relpath(path, os.path.join(source, "rules")).replace(os.sep, "/"))
    if len(sources) > 1:
        raise LayerError("the skills and rules must all come from one repo; got %s" % ", ".join(sorted(sources)))
    source = sources.pop()
    registry = _read_json(os.path.join(source, "claude", "hooks", "registry.json"))
    skills, hooks = set(asked), set()
    while True:
        before = (len(skills), len(hooks))
        for hook, entry in registry.items():
            if entry.get("origin") == "repo" and skills & set(entry.get("skills", [])):
                hooks.add(hook)
        for hook in list(hooks):
            for needed in registry.get(hook, {}).get("needs", []):
                if needed not in registry:
                    raise LayerError("hook %s needs %s, which %s does not declare" % (hook, needed, source))
                hooks.add(needed)
        for hook in hooks:
            skills.update(registry[hook].get("skills", []))
        if (len(skills), len(hooks)) == before:
            break
    for relative in skills:
        if not os.path.isfile(os.path.join(source, "skills", relative, "SKILL.md")):
            raise LayerError("a hook of %s serves skills/%s, which does not exist" % (source, relative))
    rules = asked_rules | {rule for hook in hooks for rule in registry[hook].get("rules", [])}
    return {"source": source, "registry": registry, "skills": skills, "hooks": hooks, "asked": asked,
            "rules": rules}


def _source_root(path, area="skills"):
    current = os.path.dirname(path)
    while current != os.path.dirname(current):
        if os.path.basename(current) == area:
            return os.path.dirname(current)
        current = os.path.dirname(current)
    raise LayerError("%s is not inside a %s/ folder of a skills repo" % (path, area))


def _copy_selection(root, selection):
    source = selection["source"]
    for relative in sorted(selection["skills"]):
        files = _tracked_files(source, "skills/" + relative)
        if "skills/%s/SKILL.md" % relative not in files:
            raise LayerError("skills/%s is not committed in %s: only files git tracks are copied, "
                             "so commit it first" % (relative, source))
        for file_relative in files:
            target = os.path.join(root, file_relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(source, file_relative), target)
    for relative in sorted(selection["rules"]):
        file_relative = "rules/" + relative
        if file_relative not in _tracked_files(source, file_relative):
            raise LayerError("%s is not committed in %s: only files git tracks are copied, "
                             "so commit it first" % (file_relative, source))
        target = os.path.join(root, file_relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(source, file_relative), target)
    hooks_dir = os.path.join(root, "claude", "hooks")
    registry = _read_json(os.path.join(hooks_dir, "registry.json"))
    for hook in sorted(selection["hooks"]):
        entry = selection["registry"][hook]
        for file_name in (entry["script"], entry.get("test")):
            if file_name:
                shutil.copy2(os.path.join(source, "claude", "hooks", file_name), os.path.join(hooks_dir, file_name))
        registry[hook] = dict(entry, origin="repo")
    _write_json(os.path.join(hooks_dir, "registry.json"), registry)
    wiring = _read_json(os.path.join(hooks_dir, "hooks.json"))
    source_wiring = _read_json(os.path.join(source, "claude", "hooks", "hooks.json")).get("hooks", {})
    wiring["hooks"] = merge_wiring(wiring.get("hooks", {}), select_wiring(source_wiring, selection["hooks"]))
    _write_json(os.path.join(hooks_dir, "hooks.json"), wiring)


def select_wiring(wiring, hook_names):
    """The part of a hooks.json "hooks" map that runs the given hook names."""
    selected = {}
    for event, groups in wiring.items():
        for group in groups:
            kept = [hook for hook in group.get("hooks", []) if _hook_name(hook) in hook_names]
            if kept:
                selected.setdefault(event, []).append(dict(group, hooks=kept))
    return selected


def merge_wiring(base, extra):
    """Add extra's hooks to base, joining groups that share an event and a matcher."""
    merged = json.loads(json.dumps(base))
    for event, groups in extra.items():
        for group in groups:
            target = next((existing for existing in merged.setdefault(event, [])
                           if existing.get("matcher") == group.get("matcher")), None)
            if target is None:
                merged[event].append(json.loads(json.dumps(group)))
            else:
                known = {hook["command"] for hook in target["hooks"]}
                target["hooks"].extend(hook for hook in group["hooks"] if hook["command"] not in known)
    return merged


def _hook_name(hook):
    words = (hook.get("command") or "").split()
    return words[-1] if words and any(word.strip('"').endswith("/hooks/run.py") for word in words) else None


def _tracked_files(source, relative_folder):
    """Files git tracks under the folder; every file when the source is not a git repo."""
    completed = subprocess.run(["git", "-C", source, "ls-files", "-z", "--", relative_folder],
                               capture_output=True)
    if completed.returncode == 0:
        return [path.decode() for path in completed.stdout.split(b"\0") if path]
    files = []
    for folder, subfolders, names in os.walk(os.path.join(source, relative_folder)):
        subfolders[:] = [name for name in subfolders if name not in (".git", "__pycache__", "node_modules")]
        files += [os.path.relpath(os.path.join(folder, name), source).replace(os.sep, "/") for name in names]
    return files


def refuse_traces(root, source, left_behind, keep):
    """Raise when anything under root carries a trace of source or its owner."""
    words = leaks.denylist([source], keep=keep)
    kept = {word.lower() for word in keep}
    behind = [name for name in left_behind if name.lower() not in kept]
    engine = {"claude/" + relative.replace(os.sep, "/") for relative in engine_files()}
    findings = leaks.scan(root, words, skill_names=behind, names_ignored_in=engine)
    if findings:
        raise LayerError(
            "the copied content carries traces of its source, so nothing was created:\n%s\n"
            "Remove them from the source, share what they name too (--only), or pass "
            "--allow <word> for a word that may stay." % leaks.describe(findings))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return {}


def upgrade(repo, force=False):
    """Bring repo's engine files and engine hooks up to this kit; leave the rest as it is.

    Returns {"updated", "added", "removed"}: engine file paths relative to claude/.
    """
    claude = os.path.join(os.path.abspath(repo), "claude")
    record_path = os.path.join(claude, "engine.json")
    record = _read_json(record_path).get("files")
    if record is None and not force:
        raise LayerError("%s has no claude/engine.json, so its engine files cannot be told apart from "
                         "local edits. Pass --force to replace them with the kit's." % repo)
    record = record or {}
    edited = sorted(relative for relative, digest in record.items()
                    if os.path.isfile(os.path.join(claude, relative)) and _sha256(os.path.join(claude, relative)) != digest)
    if edited and not force:
        raise LayerError("these engine files were edited in %s: %s. Move the change to the kit, or pass "
                         "--force to overwrite them." % (repo, ", ".join(edited)))
    registry, wiring = _upgraded_hooks(claude)
    _refuse_undeclared(registry, wiring)

    wanted = [relative.replace(os.sep, "/") for relative in engine_files()]
    report = {"updated": [], "added": [], "removed": []}
    hashes = {}
    for relative in wanted:
        source = os.path.join(ENGINE, relative)
        target = os.path.join(claude, relative)
        digest = _sha256(source)
        hashes[relative] = digest
        if not os.path.exists(target):
            report["added"].append(relative)
        elif _sha256(target) != digest:
            report["updated"].append(relative)
        else:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
    for relative in sorted(set(record) - set(wanted)):
        target = os.path.join(claude, relative)
        if os.path.isfile(target):
            os.remove(target)
            report["removed"].append(relative)
    _write_json(os.path.join(claude, "hooks", "registry.json"), registry)
    _write_json(os.path.join(claude, "hooks", "hooks.json"), wiring)
    if hashes != record or not os.path.exists(record_path):
        _write_json(record_path, {"source": "mAIcelium layer kit", "files": hashes})
    return {key: sorted(value) for key, value in report.items()}


def _upgraded_hooks(claude):
    """The repo's registry and hooks.json with the engine's part replaced by the kit's."""
    with open(os.path.join(ENGINE, ENGINE_HOOKS), encoding="utf-8") as handle:
        engine_hooks = json.load(handle)
    registry = _read_json(os.path.join(claude, "hooks", "registry.json"))
    old_engine = {name for name, entry in registry.items() if entry.get("origin") == "engine"}
    repo_hooks = {name: entry for name, entry in registry.items() if name not in old_engine}
    registry = dict(engine_hooks["registry"], **repo_hooks)
    current = _read_json(os.path.join(claude, "hooks", "hooks.json"))
    kept = _drop_wiring(current.get("hooks", {}), old_engine | set(engine_hooks["registry"]))
    wiring = dict(current, hooks=merge_wiring(engine_hooks["hooks"], kept))
    return registry, wiring


def _drop_wiring(wiring, hook_names):
    kept = {}
    for event, groups in wiring.items():
        for group in groups:
            hooks = [hook for hook in group.get("hooks", []) if _hook_name(hook) not in hook_names]
            if hooks:
                kept.setdefault(event, []).append(dict(group, hooks=hooks))
    return kept


def _refuse_undeclared(registry, wiring):
    wired = {_hook_name(hook) for groups in wiring.get("hooks", {}).values()
             for group in groups for hook in group.get("hooks", [])} - {None}
    missing = sorted(wired - set(registry))
    if missing:
        raise LayerError("hooks.json runs %s, which claude/hooks/registry.json does not declare; the "
                         "dispatcher would stop running it. Declare it first." % ", ".join(missing))
