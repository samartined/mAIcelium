#!/usr/bin/env python3
"""Create a new skills repo: the mAIcelium layer layout plus the engine for Claude Code.

Usage: new_layer.py <folder> [--name <plugin-name>] [--owner "<name>"]
                    [--with <skill-folder>]... [--allow <word>]...
       new_layer.py <folder> --upgrade [--force]

- <folder> is read relative to the directory `mai` was called from.
- --name is the plugin name (lowercase, digits, dashes); it defaults to the folder name.
- --owner is the repo owner's name; it defaults to git's user.name.
- --with copies a skill folder of another repo, with the hooks it needs (repeatable, or
  comma-separated). The copy is refused if it carries a trace of that repo or its owner;
  --allow <word> lets one word through.
- --upgrade replaces the engine files of an existing skills repo with this kit's, and
  its engine hooks, leaving skills, rules, its own hooks and its identity alone. It stops
  when an engine file was edited in the repo, unless --force is given.

The result is a git repo with no commit, ready for its owner to push. Exit 2 when the
request is refused (for example, a folder that already holds files).
"""
import _bootstrap  # noqa: F401

import argparse
import os
import subprocess
import sys

from _lib.layer_kit import generator


def _parse(argv):
    parser = argparse.ArgumentParser(prog="mai new-layer", description="Create a new skills repo.")
    parser.add_argument("folder")
    parser.add_argument("--name")
    parser.add_argument("--owner")
    parser.add_argument("--with", dest="with_skills", action="append", default=[])
    parser.add_argument("--allow", action="append", default=[])
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def _caller_path(path):
    return os.path.join(os.environ.get("MAICELIUM_CALLER_CWD") or os.getcwd(), os.path.expanduser(path))


def _git_user():
    completed = subprocess.run(["git", "config", "--get", "user.name"], capture_output=True, text=True)
    return completed.stdout.strip()


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    folder = os.path.abspath(_caller_path(args.folder))
    if args.upgrade:
        return _upgrade(folder, args.force)
    name = args.name or os.path.basename(folder.rstrip(os.sep))
    owner = args.owner or _git_user()
    try:
        report = generator.create(
            folder, name=name, owner=owner, allow=args.allow,
            with_skills=[_caller_path(part) for value in args.with_skills for part in value.split(",") if part],
        )
    except generator.LayerError as error:
        print("mai new-layer: %s" % error, file=sys.stderr)
        return 2
    created = report["path"]
    print("Created %s (plugin %s, owner %s)." % (created, name, owner))
    if report["skills"]:
        print("Skills: %s" % ", ".join(report["skills"]))
    if report["added"]:
        print("Added because their hooks are needed: %s" % ", ".join(report["added"]))
    if report["hooks"]:
        print("Hooks: %s" % ", ".join(report["hooks"]))
    if report["rules"]:
        print("Rules the hooks read: %s" % ", ".join(report["rules"]))
    print("Next: commit and push it, then on each machine run")
    print("  python3 %s --fix" % os.path.join(created, "claude", "doctor.py"))
    return 0


def _upgrade(folder, force):
    try:
        report = generator.upgrade(folder, force=force)
    except generator.LayerError as error:
        print("mai new-layer: %s" % error, file=sys.stderr)
        return 2
    changes = [(label, report[key]) for key, label in (
        ("updated", "Updated"), ("added", "Added"), ("removed", "Removed"))]
    for label, paths in changes:
        if paths:
            print("%s: %s" % (label, ", ".join(paths)))
    print("The engine is up to date with this kit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
