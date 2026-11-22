#!/usr/bin/env python3
"""Kits: create one, share your skills and rules in one, update one, import one.

A kit is a repo of skills and rules that works in any Claude Code session on a
machine (with or without mAIcelium) and that a mAIcelium workspace can mount as a layer.

Usage:
  kit.py create <folder> [--name <name>] [--owner "<name>"]
      An empty kit.
  kit.py share <folder> --from <your-repo> [--only <name>]... [--except <name>]...
               [--name] [--owner] [--allow <word>]...
      A kit holding your skills and rules, in the same layout, to give to someone else.
      Without --only it holds everything; each --only names `_common`, a domain (its
      skills and its rules), a skill or a rule, and --except leaves one out the same way. Skills bring the hooks and rules their
      hooks need. Nothing that identifies you may go in, and no copied text may name a
      skill or rule that stays behind: the copy is refused, saying where; --allow lets
      one word through.
  kit.py update <folder> [--force]
      Brings the repo's engine (claude/) up to this mAIcelium, leaving skills, rules
      and the repo's own hooks alone. Stops on engine files edited in the repo unless
      --force is given.
  kit.py import plan <source> [--out <map.json>]
  kit.py import apply <map.json> <folder> [--name] [--owner] [--allow <word>]...
      Converts skills and rules kept in another tool's format (Claude, Cursor, Windsurf,
      Cline, Copilot, CLAUDE.md and the like). `plan` writes a map to review and edit;
      `apply` builds the repo from it. The source is only read.

Paths are read relative to the directory `mai` was called from. --name defaults to the
folder name, --owner to git's user.name. Exit 2 when a request is refused.
"""
import _bootstrap  # noqa: F401

import argparse
import collections
import os
import subprocess
import sys

from _lib.layer_kit import generator, importer


def _caller_path(path):
    return os.path.abspath(os.path.join(os.environ.get("MAICELIUM_CALLER_CWD") or os.getcwd(),
                                        os.path.expanduser(path)))


def _git_user():
    completed = subprocess.run(["git", "config", "--get", "user.name"], capture_output=True, text=True)
    return completed.stdout.strip()


def _identity_options(parser):
    parser.add_argument("--name")
    parser.add_argument("--owner")


def _parse(argv):
    parser = argparse.ArgumentParser(prog="mai kit", description="Create, share, update or import a kit of skills and rules.")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="an empty kit")
    create.add_argument("folder")
    _identity_options(create)
    share = actions.add_parser("share", help="a kit with your skills and rules, to give away")
    share.add_argument("folder")
    share.add_argument("--from", dest="source", required=True, metavar="YOUR-REPO")
    share.add_argument("--only", action="append", default=[], metavar="NAME")
    share.add_argument("--except", dest="exclude", action="append", default=[], metavar="NAME")
    share.add_argument("--allow", action="append", default=[], metavar="WORD")
    _identity_options(share)
    update = actions.add_parser("update", help="bring a repo's engine up to this mAIcelium")
    update.add_argument("folder")
    update.add_argument("--force", action="store_true")
    imported = actions.add_parser("import", help="convert skills and rules from another tool's format")
    steps = imported.add_subparsers(dest="step", required=True)
    plan = steps.add_parser("plan", help="map a source repo")
    plan.add_argument("source")
    plan.add_argument("--out", default="layer-map.json")
    apply = steps.add_parser("apply", help="build a skills repo from a map")
    apply.add_argument("map")
    apply.add_argument("folder")
    apply.add_argument("--allow", action="append", default=[], metavar="WORD")
    _identity_options(apply)
    return parser.parse_args(argv)


def _name_and_owner(args, folder):
    return args.name or os.path.basename(folder.rstrip(os.sep)), args.owner or _git_user()


def _print_created(report, name, owner):
    print("Created %s (name %s, owner %s)." % (report["path"], name, owner))
    for key, label in (("skills", "Skills"), ("added", "Added because their hooks need them"),
                       ("hooks", "Hooks"), ("rules", "Rules")):
        if report.get(key):
            print("%s: %s" % (label, ", ".join(report[key])))
    print("Next: put it in its own git repo (for example on GitHub), then on each machine run")
    print("  python3 %s --fix" % os.path.join(report["path"], "claude", "doctor.py"))


def _create(args):
    folder = _caller_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    _print_created(generator.create(folder, name=name, owner=owner), name, owner)


def _share(args):
    folder = _caller_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    only = [part for value in args.only for part in value.split(",") if part]
    exclude = [part for value in args.exclude for part in value.split(",") if part]
    skills, rules = generator.select(_caller_path(args.source), only=only, exclude=exclude)
    report = generator.create(folder, name=name, owner=owner, with_skills=skills, with_rules=rules, allow=args.allow)
    _print_created(report, name, owner)


def _update(args):
    report = generator.upgrade(_caller_path(args.folder), force=args.force)
    for key, label in (("updated", "Updated"), ("added", "Added"), ("removed", "Removed")):
        if report[key]:
            print("%s: %s" % (label, ", ".join(report[key])))
    print("The engine is up to date with this mAIcelium.")


def _import(args):
    if args.step == "plan":
        mapping = importer.plan(_caller_path(args.source))
        out = _caller_path(args.out)
        importer.save(mapping, out)
        counts = collections.Counter(entry["kind"] for entry in mapping["items"])
        print("Mapped %d items from %s:" % (len(mapping["items"]), mapping["source"]))
        for kind, count in sorted(counts.items()):
            print("  %-22s %d" % (kind, count))
        print("Map written to %s. Review it (targets, domains, skipped sections), then run:" % out)
        print("  mai kit import apply %s <new-folder>" % args.out)
        return
    folder = _caller_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    report = importer.apply(importer.load(_caller_path(args.map)), folder, name=name, owner=owner, allow=args.allow)
    _print_created(report, name, owner)


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        {"create": _create, "share": _share, "update": _update, "import": _import}[args.action](args)
    except generator.LayerError as error:
        print("mai kit: %s" % error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
