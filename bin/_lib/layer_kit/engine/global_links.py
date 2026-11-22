"""Personal links from ~/.claude/skills/ to this repo's skills.

Every folder under skills/ that holds a SKILL.md gets one link in the personal skills
folder, so any Claude Code session sees it wherever it starts. Claude Code lists a
personal and a project skill once when they share a folder name or resolve to the same
folder (pinned in tests/test_live_platform.py). So, when a workspace such as mAIcelium
reflects a skill under another name, the link learns and takes that name: both copies
then coincide on both keys and load once.

Only links this engine created, recorded in a manifest, are ever changed or removed.
Anything else in the personal skills folder is left as it is and reported as a conflict
when it takes a name the engine wants.
"""

import contextlib
import fcntl
import json
import os
import secrets
import time

MANIFEST = "manifest.json"
ALIASES = "aliases.json"
LOCK = "links.lock"
LOCK_WAIT_SECONDS = 5


def load_exclusions(repo_root):
    try:
        with open(os.path.join(repo_root, "claude", "global.json"), encoding="utf-8") as handle:
            return list(json.load(handle).get("exclude", []))
    except FileNotFoundError:
        return []


def discover_skills(repo_root, exclude=()):
    found = {}
    for folder, subfolders, files in os.walk(os.path.join(repo_root, "skills")):
        subfolders.sort()
        name = os.path.basename(folder)
        if "SKILL.md" in files and name not in exclude:
            found[name] = folder
    return found


def learn_aliases(project_dir, repo_root, state_dir):
    """Record the names a workspace gives to this repo's skill folders."""
    reflections = os.path.join(project_dir, ".claude", "skills")
    if not os.path.isdir(reflections):
        return
    skills_root = os.path.realpath(os.path.join(repo_root, "skills"))
    aliases = _load(state_dir, ALIASES)
    learnt = dict(aliases)
    for entry in sorted(os.listdir(reflections)):
        target = os.path.realpath(os.path.join(reflections, entry))
        if target.startswith(skills_root + os.sep) and os.path.isfile(os.path.join(target, "SKILL.md")):
            learnt[os.path.relpath(target, skills_root)] = entry
    if learnt != aliases:
        _save(state_dir, ALIASES, learnt)


def sync(repo_root, skills_dir, state_dir, exclude=()):
    """Make the personal links match the repo; return what changed and what was refused."""
    report = {"created": [], "updated": [], "removed": [], "conflicts": [], "errors": []}
    try:
        with _locked(state_dir) as acquired:
            if not acquired:
                report["errors"].append("another session holds the link lock")
                return report
            os.makedirs(skills_dir, exist_ok=True)
            manifest = _load(state_dir, MANIFEST)
            desired = _desired_links(repo_root, state_dir, exclude)
            _retire_links(manifest, desired, skills_dir, report)
            _place_links(manifest, desired, skills_dir, report)
            _save(state_dir, MANIFEST, manifest)
    except OSError as error:
        report["errors"].append(str(error))
    return report


def owned_links(state_dir):
    """The links this engine created: name -> skill folder."""
    return _load(state_dir, MANIFEST)


def load_state(state_dir, name):
    return _load(state_dir, name)


def save_state(state_dir, name, data):
    _save(state_dir, name, data)


def desired_links(repo_root, state_dir, exclude=()):
    """The links the repo wants right now: name -> skill folder."""
    return _desired_links(repo_root, state_dir, exclude)


def _desired_links(repo_root, state_dir, exclude):
    skills_root = os.path.realpath(os.path.join(repo_root, "skills"))
    aliases = _load(state_dir, ALIASES)
    desired = {}
    for name, folder in discover_skills(repo_root, exclude).items():
        relative = os.path.relpath(os.path.realpath(folder), skills_root)
        desired[aliases.get(relative, name)] = folder
    return desired


def _retire_links(manifest, desired, skills_dir, report):
    """Remove our links that the repo no longer wants, if nobody retargeted them."""
    for name, target in sorted(manifest.items()):
        if name in desired:
            continue
        path = os.path.join(skills_dir, name)
        if os.path.islink(path) and os.readlink(path) == target:
            try:
                os.remove(path)
            except OSError as error:
                report["errors"].append("%s: %s" % (name, error))
                continue
            report["removed"].append(name)
        del manifest[name]


def _place_links(manifest, desired, skills_dir, report):
    for name, folder in sorted(desired.items()):
        path = os.path.join(skills_dir, name)
        try:
            if not os.path.lexists(path):
                _link(folder, path)
                report["created"].append(name)
            elif not os.path.islink(path):
                report["conflicts"].append(name)
                manifest.pop(name, None)
                continue
            elif os.readlink(path) != folder:
                if manifest.get(name) != os.readlink(path):
                    report["conflicts"].append(name)
                    manifest.pop(name, None)
                    continue
                _link(folder, path)
                report["updated"].append(name)
            manifest[name] = folder
        except OSError as error:
            report["errors"].append("%s: %s" % (name, error))


def _link(target, path):
    """Point path at target in one atomic step, replacing a previous link of ours."""
    temporary = os.path.join(os.path.dirname(path), ".%s.%s" % (os.path.basename(path), secrets.token_hex(4)))
    os.symlink(target, temporary)
    try:
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.remove(temporary)


@contextlib.contextmanager
def _locked(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, LOCK), "a") as handle:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    yield False
                    return
                time.sleep(0.02)
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _load(state_dir, name):
    try:
        with open(os.path.join(state_dir, name), encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return {}


def _save(state_dir, name, data):
    os.makedirs(state_dir, exist_ok=True)
    temporary = os.path.join(state_dir, ".%s.%s" % (name, secrets.token_hex(4)))
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    os.replace(temporary, os.path.join(state_dir, name))
