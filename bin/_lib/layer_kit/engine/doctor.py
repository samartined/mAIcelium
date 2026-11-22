#!/usr/bin/env python3
"""Check and fix how this machine consumes the repo.

  python3 claude/doctor.py              report; exit 1 when something needs attention
  python3 claude/doctor.py --fix        link the plugin and the skills, retire manual
                                        registrations of the hooks the plugin delivers
                                        (the settings file is backed up first), and import
                                        claude/hard-rules.md from ~/.claude/CLAUDE.md
                                        (backed up first when it exists)
  python3 claude/doctor.py --uninstall  remove the plugin link, this repo's skill links, the
                                        hard rules import and the engine's state

--fix is also the one command that sets a new machine up. Every option only touches
what belongs to this repo: anything else found on the way is reported, never changed.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "hooks"))

import global_links  # noqa: E402
import identity  # noqa: E402
import run  # noqa: E402

PLUGIN_LINK = identity.name(HERE)
SETTINGS_FILES = ("settings.json", "settings.local.json")
LAST_SYNC = "last_sync.json"
PULL = "pull.json"
LIVE = "live_check.json"
LAST_ERROR = "last_error.txt"


def diagnose(repo_root, home, state_dir):
    skills_dir = _skills_dir(home)
    last_error = os.path.join(state_dir, LAST_ERROR)
    return {
        "plugin": _plugin_state(repo_root, skills_dir),
        "branch": _branch(repo_root),
        "missing_links": _missing_links(repo_root, skills_dir, state_dir),
        "conflicts": global_links.load_state(state_dir, LAST_SYNC).get("conflicts", []),
        "legacy": sorted({script for _, script in _legacy_registrations(repo_root, home)}),
        "pull": global_links.load_state(state_dir, PULL).get("status"),
        "live": global_links.load_state(state_dir, LIVE),
        "last_error": _last_line(last_error) if os.path.exists(last_error) else None,
        "hard_rules": "ok" if _hard_rules_import_lines(repo_root, home) else "missing",
    }


def healthy(diagnosis):
    live = diagnosis["live"]
    return (
        diagnosis["plugin"] == "ok"
        and diagnosis["branch"] == "main"
        and not diagnosis["missing_links"]
        and not diagnosis["conflicts"]
        and not diagnosis["legacy"]
        and diagnosis["pull"] != "diverged"
        and not (live and not live.get("passed"))
        and diagnosis["hard_rules"] == "ok"
    )


def format_report(diagnosis):
    live = diagnosis["live"]
    lines = [
        "plugin link: %s" % diagnosis["plugin"],
        "live tree branch: %s" % (diagnosis["branch"] or "unknown"),
        "skill links: %s" % ("all in place" if not diagnosis["missing_links"]
                             else "missing " + ", ".join(diagnosis["missing_links"])),
        "conflicts: %s" % (", ".join(diagnosis["conflicts"]) or "none"),
        "manual registrations of delivered hooks: %s" % (", ".join(diagnosis["legacy"]) or "none"),
        "hard rules import: %s" % diagnosis["hard_rules"],
        "last pull: %s" % (diagnosis["pull"] or "never"),
        "last live check: %s" % ("%s %s" % (live["version"], "passed" if live.get("passed") else "FAILED")
                                 if live else "never"),
    ]
    if diagnosis["last_error"]:
        lines.append("last error: %s" % diagnosis["last_error"])
    lines.append("status: %s" % ("healthy" if healthy(diagnosis) else "needs attention"))
    return "\n".join(lines)


def fix(repo_root, home, state_dir):
    skills_dir = _skills_dir(home)
    actions = []
    os.makedirs(skills_dir, exist_ok=True)
    plugin = _plugin_state(repo_root, skills_dir)
    if plugin == "missing":
        os.symlink(os.path.join(repo_root, "claude"), os.path.join(skills_dir, PLUGIN_LINK))
        actions.append("linked the plugin")
    elif plugin == "foreign":
        actions.append("left alone: %s is not this repo's plugin link" % os.path.join(skills_dir, PLUGIN_LINK))
    report = global_links.sync(repo_root, skills_dir, state_dir, exclude=global_links.load_exclusions(repo_root))
    if report["created"] or report["updated"] or report["removed"]:
        actions.append("synced skill links: %d created, %d updated, %d removed"
                       % (len(report["created"]), len(report["updated"]), len(report["removed"])))
    for path in _settings_paths(home):
        removed = _retire_legacy(path, _delivered_scripts(repo_root))
        if removed:
            actions.append("removed %d manual hook registration(s) from %s (backup kept)" % (removed, path))
    if not _hard_rules_import_lines(repo_root, home):
        _add_hard_rules_import(repo_root, home)
        actions.append("imported the hard rules in %s" % _claude_md(home))
    return actions


def uninstall(repo_root, home, state_dir):
    skills_dir = _skills_dir(home)
    actions = []
    if _plugin_state(repo_root, skills_dir) == "ok":
        os.remove(os.path.join(skills_dir, PLUGIN_LINK))
        actions.append("removed the plugin link")
    for name, target in sorted(global_links.owned_links(state_dir).items()):
        path = os.path.join(skills_dir, name)
        if os.path.islink(path) and os.readlink(path) == target:
            os.remove(path)
            actions.append("removed the skill link %s" % name)
    if _remove_hard_rules_import(repo_root, home):
        actions.append("removed the hard rules import from %s (backup kept)" % _claude_md(home))
    shutil.rmtree(state_dir, ignore_errors=True)
    return actions


def _skills_dir(home):
    return os.path.join(home, ".claude", "skills")


def _settings_paths(home):
    return [os.path.join(home, ".claude", name) for name in SETTINGS_FILES]


def _plugin_state(repo_root, skills_dir):
    path = os.path.join(skills_dir, PLUGIN_LINK)
    if not os.path.lexists(path):
        return "missing"
    if os.path.islink(path) and os.path.realpath(path) == os.path.realpath(os.path.join(repo_root, "claude")):
        return "ok"
    return "foreign"


def _branch(repo_root):
    completed = subprocess.run(
        ["git", "-C", repo_root, "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return completed.stdout.strip() or None


def _missing_links(repo_root, skills_dir, state_dir):
    desired = global_links.desired_links(repo_root, state_dir, global_links.load_exclusions(repo_root))
    return sorted(
        name for name, folder in desired.items()
        if not (os.path.islink(os.path.join(skills_dir, name)) and os.readlink(os.path.join(skills_dir, name)) == folder)
    )


def _delivered_scripts(repo_root):
    hooks_dir = os.path.join(repo_root, "claude", "hooks")
    hooks = identity.hooks(os.path.join(repo_root, "claude"))
    return {os.path.realpath(os.path.join(hooks_dir, name)) for name in hooks.values()}


def _refers_to(command, scripts):
    return any(
        os.path.realpath(os.path.expanduser(os.path.expandvars(token))) in scripts
        for token in run._tokens(command)
    )


def _legacy_registrations(repo_root, home):
    scripts = _delivered_scripts(repo_root)
    found = []
    for path in _settings_paths(home):
        settings = _read_json(path)
        for groups in (settings.get("hooks") or {}).values():
            for group in groups or []:
                for hook in group.get("hooks") or []:
                    for token in run._tokens(hook.get("command") or ""):
                        resolved = os.path.realpath(os.path.expanduser(os.path.expandvars(token)))
                        if resolved in scripts:
                            found.append((path, token))
    return found


def _retire_legacy(path, scripts):
    settings = _read_json(path)
    if not settings:
        return 0
    removed = 0
    kept_events = {}
    for event, groups in (settings.get("hooks") or {}).items():
        kept_groups = []
        for group in groups or []:
            hooks = group.get("hooks") or []
            kept = [hook for hook in hooks if not _refers_to(hook.get("command") or "", scripts)]
            removed += len(hooks) - len(kept)
            if kept:
                kept_groups.append(dict(group, hooks=kept))
        if kept_groups:
            kept_events[event] = kept_groups
    if removed:
        shutil.copy2(path, "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S")))
        settings["hooks"] = kept_events
        temporary = "%s.%s" % (path, secrets.token_hex(4))
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    return removed


def _claude_md(home):
    return os.path.join(home, ".claude", "CLAUDE.md")


def _hard_rules_path(repo_root):
    return os.path.realpath(os.path.join(repo_root, "claude", "hard-rules.md"))


def _read_lines(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().splitlines(keepends=True)
    except FileNotFoundError:
        return []


def _imports_hard_rules(line, repo_root, home):
    """True when `line` is an `@` import whose path, `~` read as `home`, is this repo's hard rules."""
    text = line.strip()
    if not text.startswith("@"):
        return False
    target = text[1:]
    if target == "~" or target.startswith("~/"):
        target = home + target[1:]
    return os.path.realpath(target) == _hard_rules_path(repo_root)


def _hard_rules_import_lines(repo_root, home):
    return [line for line in _read_lines(_claude_md(home)) if _imports_hard_rules(line, repo_root, home)]


def _write_with_backup(path, lines):
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S")))
    temporary = "%s.%s" % (path, secrets.token_hex(4))
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    os.replace(temporary, path)


def _add_hard_rules_import(repo_root, home):
    path = _claude_md(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    target = _hard_rules_path(repo_root)
    real_home = os.path.realpath(home)
    if target.startswith(real_home + os.sep):
        target = "~" + target[len(real_home):]
    lines = _read_lines(path)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    _write_with_backup(path, lines + ["@%s\n" % target])


def _remove_hard_rules_import(repo_root, home):
    path = _claude_md(home)
    lines = _read_lines(path)
    kept = [line for line in lines if not _imports_hard_rules(line, repo_root, home)]
    if len(kept) == len(lines):
        return False
    _write_with_backup(path, kept)
    return True


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def _last_line(path):
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    return lines[-1] if lines else None


def main(argv):
    home = os.path.expanduser("~")
    state_dir = identity.state_dir(HERE, os.environ)
    if "--uninstall" in argv:
        print("\n".join(uninstall(REPO, home, state_dir)) or "nothing to remove")
        return 0
    if "--fix" in argv:
        print("\n".join(fix(REPO, home, state_dir)) or "nothing to fix")
    diagnosis = diagnose(REPO, home, state_dir)
    print(format_report(diagnosis))
    return 0 if healthy(diagnosis) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
