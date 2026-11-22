"""Traces of whoever builds a skills repo, found before the repo is handed over.

Whatever the kit copies from someone's own repos (skills given with `share`, a repo
converted with `import`) may carry their identity: their name or email, their home
folder, the name or remote of their private repo, or the names of skills they kept for
themselves. The words to look for are worked out from the sources and the machine, so
nobody keeps a list. The new owner's name, and any word passed explicitly, are left out.
"""

import collections
import json
import os
import re
import subprocess

MIN_LENGTH = 3
TEXT_LIMIT_BYTES = 2_000_000
Finding = collections.namedtuple("Finding", "path line word")


def denylist(sources, keep=(), environ=None):
    """Words that identify the builder or their sources, minus `keep`."""
    environ = os.environ if environ is None else environ
    words = set()
    home = environ.get("HOME") or os.path.expanduser("~")
    if home and home != os.sep:
        words.add(os.path.realpath(home))
        words.add(home)
    for source in sources:
        words.update(_git_config(source, "user.name", "user.email"))
        words.add(os.path.basename(os.path.realpath(source)))
        words.update(_remote_parts(source))
        manifest = _read_json(os.path.join(source, "claude", ".claude-plugin", "plugin.json"))
        words.add(manifest.get("name") or "")
        words.add((manifest.get("author") or {}).get("name") or "")
    kept = {word.strip().lower() for word in keep if word}
    return sorted(word for word in words if len(word.strip()) >= MIN_LENGTH and word.strip().lower() not in kept)


def left_behind_skills(source, selected):
    """Skill folder names in source that are not being copied.

    selected: the copied skills, as paths under skills/ ("_domains/ops/guard") or bare
    names. A skill whose folder holds a copied skill (a domain folder that is a skill too)
    is not counted: its name is in the copied paths anyway.
    """
    chosen = [entry.replace(os.sep, "/") for entry in selected]
    chosen_names = {os.path.basename(entry) for entry in chosen}
    skills_root = os.path.join(source, "skills")
    names = set()
    for folder, _, files in os.walk(skills_root):
        if "SKILL.md" not in files:
            continue
        relative = os.path.relpath(folder, skills_root).replace(os.sep, "/")
        if any(entry.startswith(relative + "/") for entry in chosen):
            continue
        names.add(os.path.basename(folder))
    return sorted(names - chosen_names)


def scan(root, words, skill_names=(), names_ignored_in=()):
    """Every line under root that holds a word, or names a left-behind skill as a path or code.

    names_ignored_in: files (relative to root, with /) where skill names are not looked
    for, such as the kit's own engine, whose paths are not anyone's skills.
    """
    word_patterns = [(word, _word_pattern(word)) for word in words]
    name_patterns = [(name, re.compile(r"(?:/%s(?:/|$)|`%s`)" % (re.escape(name), re.escape(name))))
                     for name in skill_names]
    ignored = set(names_ignored_in)
    findings = []
    for folder, subfolders, names in _walk(root):
        for file_name in sorted(names):
            path = os.path.join(folder, file_name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            patterns = word_patterns + ([] if relative in ignored else name_patterns)
            for word, pattern in patterns:
                if pattern.search("/" + relative):
                    findings.append(Finding(relative, 0, word))
            for number, line in enumerate(_lines(path), 1):
                for word, pattern in patterns:
                    if pattern.search(line.replace("\\", "/")):
                        findings.append(Finding(relative, number, word))
    return findings


def describe(findings, limit=20):
    lines = ["%s:%s: %s" % (finding.path, finding.line or "(name)", finding.word) for finding in findings[:limit]]
    if len(findings) > limit:
        lines.append("... and %d more" % (len(findings) - limit))
    return "\n".join(lines)


def _word_pattern(word):
    escaped = re.escape(word)
    if word[:1].isalnum():
        escaped = r"(?<![\w])" + escaped
    if word[-1:].isalnum():
        escaped += r"(?![\w])"
    return re.compile(escaped, re.IGNORECASE)


def _walk(root):
    for folder, subfolders, names in os.walk(root):
        subfolders[:] = sorted(name for name in subfolders if name not in (".git", "__pycache__"))
        yield folder, subfolders, names


def _lines(path):
    try:
        if os.path.getsize(path) > TEXT_LIMIT_BYTES:
            return []
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return []
    if b"\0" in data[:4096]:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def _git_config(source, *keys):
    values = []
    for key in keys:
        completed = subprocess.run(["git", "-C", source, "config", "--get", key], capture_output=True, text=True)
        if completed.returncode == 0:
            values.append(completed.stdout.strip())
    return values


def _remote_parts(source):
    completed = subprocess.run(["git", "-C", source, "remote", "get-url", "origin"], capture_output=True, text=True)
    url = completed.stdout.strip()
    if completed.returncode != 0 or not url:
        return []
    path = re.split(r"[:/]", re.sub(r"\.git$", "", url))
    return [part for part in path[-2:] if part and "@" not in part and "." not in part]


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return {}
