#!/usr/bin/env python3
"""Convert a repo of skills and rules, in any agent's format, into a skills repo.

Usage:
  import_layer.py plan <source> [--out <map.json>]
  import_layer.py apply <map.json> <folder> [--name <plugin-name>] [--owner "<name>"] [--allow <word>]...

`plan` reads <source> and writes a map (default layer-map.json) of every file found: what
it is, what it becomes and where it goes. Read it, edit any `to`, `action` or section,
then `apply` builds the new repo from it, with the engine for Claude Code. The source is
never changed. Paths are read relative to the directory `mai` was called from.
Exit 2 when the request is refused.
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


def _parse(argv):
    parser = argparse.ArgumentParser(prog="mai import-layer")
    steps = parser.add_subparsers(dest="step", required=True)
    plan = steps.add_parser("plan", help="map a source repo")
    plan.add_argument("source")
    plan.add_argument("--out", default="layer-map.json")
    apply = steps.add_parser("apply", help="build a skills repo from a map")
    apply.add_argument("map")
    apply.add_argument("folder")
    apply.add_argument("--name")
    apply.add_argument("--owner")
    apply.add_argument("--allow", action="append", default=[])
    return parser.parse_args(argv)


def _plan(args):
    mapping = importer.plan(_caller_path(args.source))
    out = _caller_path(args.out)
    importer.save(mapping, out)
    counts = collections.Counter(entry["kind"] for entry in mapping["items"])
    print("Mapped %d items from %s:" % (len(mapping["items"]), mapping["source"]))
    for kind, count in sorted(counts.items()):
        print("  %-22s %d" % (kind, count))
    print("Map written to %s. Review it (targets, domains, skipped sections), then run:" % out)
    print("  mai import-layer apply %s <new-folder>" % args.out)
    return 0


def _apply(args):
    mapping = importer.load(_caller_path(args.map))
    folder = _caller_path(args.folder)
    owner = args.owner or subprocess.run(["git", "config", "--get", "user.name"],
                                         capture_output=True, text=True).stdout.strip()
    report = importer.apply(mapping, folder, name=args.name or os.path.basename(folder.rstrip(os.sep)),
                            owner=owner, allow=args.allow)
    print("Created %s." % report["path"])
    print("Next: commit and push it, then on each machine run")
    print("  python3 %s --fix" % os.path.join(report["path"], "claude", "doctor.py"))
    return 0


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        return _plan(args) if args.step == "plan" else _apply(args)
    except generator.LayerError as error:
        print("mai import-layer: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
