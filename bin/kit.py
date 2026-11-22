#!/usr/bin/env python3
"""Kits: create one, share your skills and rules in one, update one, import one.

A kit is a repo of skills and rules that works in any Claude Code session on a machine
(with or without mAIcelium) and that a mAIcelium workspace can mount as a layer.

Usage:
  kit.py create <folder> [--name <name>] [--owner "<name>"]
      An empty kit: the layer layout, the engine in claude/ and a README and AGENTS.md.
  kit.py share <folder> --owner "<name>" --from <your-repo>
               [--only <name>]... [--except <name>]... [--allow <word>]... [--name <name>]
      A kit with your skills and rules, in the same layout, for someone else (--owner is
      required). Without --only it holds everything; each --only names `_common`, a
      domain (its skills and its rules), a skill or a rule, and each --except leaves one
      out the same way. Skills bring the hooks that serve them and the rules those hooks
      read. Nothing that identifies you or your repo may go in, and no copied text may
      name a skill or rule left behind: the copy is refused, saying which file and line;
      --allow lets one word through.
  kit.py update <folder> [--force]
      Brings the kit's engine (claude/) up to this mAIcelium, leaving its skills, rules,
      own hooks and settings alone. Stops on engine files edited in the kit unless
      --force is given.
  kit.py import plan <source> [--out <map.json>]
  kit.py import apply <map.json> <folder> [--name <name>] [--owner "<name>"] [--allow <word>]...
      Converts skills and rules kept in another tool's format (Claude Code, Cursor,
      Windsurf, Cline, Copilot, CLAUDE.md and the like). `plan` writes a map to review
      and edit; `apply` builds the kit from it. The source is only read.

--owner is the person the kit belongs to: it names the README, AGENTS.md, hard-rules.md
and the plugin's author. It defaults to git's user.name, except in `share`, where it is
required. --name is the kit's plugin name (lowercase letters, digits and dashes): the
name of its link under ~/.claude/skills, of its state folder and the prefix of its
messages. It defaults to the folder name.

Where kits go: a bare name (`devops-for-alex`) means `<workspace>/kits/devops-for-alex`, a folder
git ignores, so a kit never ends up in the workspace's own repo. A path is read relative
to the directory `mai` was called from and, inside the workspace, must be under kits/.
The import map follows the same rule. Exit 2 when a request is refused.
"""
import _bootstrap  # noqa: F401

import argparse
import collections
import os
import subprocess
import sys

from _lib.layer_kit import generator, importer
from _lib.platform import resolve_root

KITS = "kits"


def _caller_path(path):
    return os.path.abspath(os.path.join(os.environ.get("MAICELIUM_CALLER_CWD") or os.getcwd(),
                                        os.path.expanduser(path)))


def _kit_path(path):
    """Where a kit (or an import map) given on the command line goes."""
    root = os.path.realpath(resolve_root())
    kits = os.path.join(root, KITS)
    if not os.path.isabs(path) and not os.path.dirname(path) and not path.startswith("~") and path not in (".", ".."):
        os.makedirs(kits, exist_ok=True)
        return os.path.join(kits, path)
    full = os.path.realpath(_caller_path(path))
    if _inside(full, root) and not _inside(full, kits):
        raise generator.LayerError(
            "%s is inside the mAIcelium workspace, whose own git repo may be public. Put kits in "
            "%s/ (a bare name goes there) or outside the workspace." % (full, kits))
    return full


def _inside(path, folder):
    return path == folder or path.startswith(folder + os.sep)


def _git_user():
    completed = subprocess.run(["git", "config", "--get", "user.name"], capture_output=True, text=True)
    return completed.stdout.strip()


NAME_HELP = "the kit's plugin name (default: the folder name)"
FOLDER_HELP = "a bare name goes to <workspace>/kits/; a path is read from where mai was called"


def _identity_options(parser):
    parser.add_argument("--name", help=NAME_HELP)
    parser.add_argument("--owner", help="who the kit belongs to (default: git's user.name)")


def _parse(argv):
    parser = argparse.ArgumentParser(prog="mai kit", description="Create, share, update or import a kit of skills and rules.")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="an empty kit")
    create.add_argument("folder", help=FOLDER_HELP)
    _identity_options(create)
    share = actions.add_parser("share", help="a kit with your skills and rules, to give away")
    share.add_argument("folder", help=FOLDER_HELP)
    share.add_argument("--owner", required=True, help="who the kit is for (required)")
    share.add_argument("--from", dest="source", required=True, metavar="YOUR-REPO",
                       help="the repo (or mesh layer) to copy skills and rules from")
    share.add_argument("--only", action="append", default=[], metavar="NAME",
                       help="_common, a domain, a skill or a rule to share (repeatable; default: all)")
    share.add_argument("--except", dest="exclude", action="append", default=[], metavar="NAME",
                       help="_common, a domain, a skill or a rule to leave out (repeatable)")
    share.add_argument("--allow", action="append", default=[], metavar="WORD",
                       help="a word the trace check may let through (repeatable)")
    share.add_argument("--name", help=NAME_HELP)
    update = actions.add_parser("update", help="bring a kit's engine up to this mAIcelium")
    update.add_argument("folder", help=FOLDER_HELP)
    update.add_argument("--force", action="store_true", help="overwrite engine files edited in the kit")
    imported = actions.add_parser("import", help="convert skills and rules from another tool's format")
    steps = imported.add_subparsers(dest="step", required=True)
    plan = steps.add_parser("plan", help="map a source repo; reads it only")
    plan.add_argument("source", help="the repo whose skills and rules to convert")
    plan.add_argument("--out", default="layer-map.json", help="the map to write (default: kits/layer-map.json)")
    apply = steps.add_parser("apply", help="build a kit from a reviewed map")
    apply.add_argument("map", help="the map written by plan")
    apply.add_argument("folder", help=FOLDER_HELP)
    apply.add_argument("--allow", action="append", default=[], metavar="WORD",
                       help="a word the trace check may let through (repeatable)")
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
    folder = _kit_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    _print_created(generator.create(folder, name=name, owner=owner), name, owner)


def _share(args):
    folder = _kit_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    only = [part for value in args.only for part in value.split(",") if part]
    exclude = [part for value in args.exclude for part in value.split(",") if part]
    skills, rules = generator.select(_caller_path(args.source), only=only, exclude=exclude)
    report = generator.create(folder, name=name, owner=owner, with_skills=skills, with_rules=rules, allow=args.allow)
    _print_created(report, name, owner)


def _update(args):
    report = generator.upgrade(_kit_path(args.folder), force=args.force)
    for key, label in (("updated", "Updated"), ("added", "Added"), ("removed", "Removed")):
        if report[key]:
            print("%s: %s" % (label, ", ".join(report[key])))
    print("The engine is up to date with this mAIcelium.")


def _import(args):
    if args.step == "plan":
        mapping = importer.plan(_caller_path(args.source))
        out = _kit_path(args.out)
        importer.save(mapping, out)
        counts = collections.Counter(entry["kind"] for entry in mapping["items"])
        print("Mapped %d items from %s:" % (len(mapping["items"]), mapping["source"]))
        for kind, count in sorted(counts.items()):
            print("  %-22s %d" % (kind, count))
        print("Map written to %s. Review it (targets, domains, skipped sections), then run:" % out)
        print("  mai kit import apply %s <new-folder>" % args.out)
        return
    folder = _kit_path(args.folder)
    name, owner = _name_and_owner(args, folder)
    report = importer.apply(importer.load(_kit_path(args.map)), folder, name=name, owner=owner, allow=args.allow)
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
