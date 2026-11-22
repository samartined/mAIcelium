#!/usr/bin/env python3
"""Fail when tracked text or commit metadata carries personal or client traces.

This repo is public. Generic shapes are always checked: personal home paths, real
email addresses and, in commits, AI attribution and identities that are not a GitHub
noreply address. Names no pattern can know (clients, employers, colleagues) come
from the PRIVATE_WORDS environment variable (one per line or comma-separated, kept
as a CI secret) or from --words-from FILE (a JSON with a "private_words" list, such
as a personal layer's claude/global.json). Those names are never written here.

Usage:
    check_public_text.py [--words-from FILE] [--commits RANGE] [PATH ...]

With no PATH, every file tracked by git is checked. Exit status 1 when anything is
found.
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import collections
import json
import os
import re
import subprocess
import sys

from _lib.layer_kit.leaks import _word_pattern

Finding = collections.namedtuple("Finding", "where line kind text")

# A home folder followed by a real user name. Placeholders used in docs and tests
# (/home/user, /Users/<name>, $USER, the CI runner) are not anyone's home.
_PLACEHOLDER_USERS = r"(?:user|users|you|me|name|username|runner|example|alice|bob|grace)\b"
HOME_PATH = re.compile(r"(?:/Users|/home)/(?!" + _PLACEHOLDER_USERS + r")[A-Za-z0-9][\w.-]*", re.IGNORECASE)

EMAIL = re.compile(r"(?<![\w.+-])([\w.+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# RFC 2606 / 6761 reserved names, GitHub noreply, and git's ssh user.
_RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
_RESERVED_SUFFIXES = (".example", ".invalid", ".test", ".localhost", ".example.com")
NOREPLY_DOMAINS = ("users.noreply.github.com", "noreply.github.com", "github.com")

AI_ATTRIBUTION = re.compile(
    r"co-authored-by:.*(?:claude|anthropic|openai|copilot|gemini)|generated (?:with|by) \[?claude"
    r"|claude\.ai/code/session_|^claude-session:",
    re.IGNORECASE | re.MULTILINE,
)


def _email_allowed(local, domain):
    domain = domain.lower().rstrip(".")
    if local == "git":
        return True
    if domain in _RESERVED_DOMAINS or domain.endswith(_RESERVED_SUFFIXES):
        return True
    return domain.endswith("users.noreply.github.com")


def load_words(words_from=None, environ=None):
    environ = os.environ if environ is None else environ
    words = set()
    for chunk in re.split(r"[\n,]", environ.get("PRIVATE_WORDS", "")):
        if chunk.strip():
            words.add(chunk.strip())
    if words_from:
        with open(words_from, encoding="utf-8") as handle:
            words.update(w.strip() for w in json.load(handle).get("private_words") or [] if w.strip())
    return sorted(words)


def compile_words(words):
    return [(w, _word_pattern(w)) for w in words if len(w.strip()) >= 3]


def scan_text(where, text, words):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        normalized = line.replace("\\", "/")
        if HOME_PATH.search(normalized):
            found.append(Finding(where, number, "home path", line.strip()))
        for match in EMAIL.finditer(line):
            if not _email_allowed(match.group(1), match.group(2)):
                found.append(Finding(where, number, "email", line.strip()))
                break
        for word, pattern in words:
            if pattern.search(normalized):
                found.append(Finding(where, number, "private word", word))
    return found


def tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True, check=True)
    return [os.path.join(root, p) for p in out.stdout.split("\0") if p]


def scan_files(paths, words, root=None):
    found = []
    for path in paths:
        where = os.path.relpath(path, root) if root else path
        try:
            with open(path, "rb") as handle:
                data = handle.read(4_000_000)
        except (IsADirectoryError, FileNotFoundError):
            continue
        if b"\0" in data[:8000]:
            continue
        found.extend(scan_text(where, data.decode("utf-8", "replace"), words))
        for word, pattern in words:
            if pattern.search("/" + where.replace("\\", "/")):
                found.append(Finding(where, 0, "private word in path", word))
    return found


def scan_commits(root, revision_range, words):
    out = subprocess.run(
        ["git", "-C", root, "log", "--format=%H%x00%ae%x00%ce%x00%B%x01", revision_range],
        capture_output=True, text=True, check=True,
    ).stdout
    found = []
    for record in out.split("\x01"):
        record = record.strip("\n")
        if not record:
            continue
        sha, author, committer, message = record.split("\0", 3)
        where = "commit " + sha[:8]
        for role, email in (("author", author), ("committer", committer)):
            domain = email.rsplit("@", 1)[-1].lower()
            if domain not in NOREPLY_DOMAINS and not domain.endswith("users.noreply.github.com"):
                found.append(Finding(where, 0, "identity", f"{role} {email}"))
        if AI_ATTRIBUTION.search(message):
            found.append(Finding(where, 0, "ai attribution", message.strip().splitlines()[0]))
        found.extend(f._replace(where=where) for f in scan_text(where, message, words))
    return found


def describe(findings, limit=50):
    rows = []
    for f in findings[:limit]:
        place = f"{f.where}:{f.line}" if f.line else f.where
        rows.append(f"{place}: {f.kind}: {f.text[:120]}")
    if len(findings) > limit:
        rows.append(f"... and {len(findings) - limit} more")
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="files to check (default: every tracked file)")
    parser.add_argument("--words-from", help='JSON file with a "private_words" list')
    parser.add_argument("--commits", help="also check commits in this git revision range")
    args = parser.parse_args(argv)

    root = _bootstrap.WORKSPACE_ROOT
    words = compile_words(load_words(args.words_from))
    if args.paths:
        findings = scan_files(args.paths, words)
    else:
        findings = scan_files(tracked_files(root), words, root=root)
    if args.commits:
        findings += scan_commits(root, args.commits, words)
    if findings:
        print(describe(findings))
        print(f"\n{len(findings)} trace(s) found. This repo is public: use neutral names "
              f"(acme, globex), ~ or /home/user for paths, and a noreply email.", file=sys.stderr)
        return 1
    print(f"No personal or client traces ({len(words)} private word(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
