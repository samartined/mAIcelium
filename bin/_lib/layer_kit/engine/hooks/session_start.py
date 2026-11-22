#!/usr/bin/env python3
"""SessionStart hook of this repo's plugin: keep this repo's skills reachable.

At every session start, on any machine and wherever the session opens, it:
- learns the names the current workspace gives this repo's skills (see global_links);
- brings the personal skill links in line with the repo;
- starts the background maintenance (git pull, live checks) at most once per interval;
- says one line only when the owner has to act: a link conflict that survived two session
  starts, or a personal skill hiding a different skill of the open project.

It never blocks and never fails a session start: an error is written to the state
folder and the session starts as if nothing happened.
"""

import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.realpath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(CLAUDE_DIR)
sys.path.insert(0, CLAUDE_DIR)

import global_links  # noqa: E402
import identity  # noqa: E402

MAINTENANCE_INTERVAL_SECONDS = 1800
MAINTENANCE = os.path.join(CLAUDE_DIR, "maintenance.py")
LAST_SYNC = "last_sync.json"
WARNED = "warned.json"
MAINTENANCE_STAMP = "maintenance.json"
LAST_ERROR = "last_error.txt"
LIVE_CHECK = "live_check.json"
PULL = "pull.json"


def handle(payload, repo_root, skills_dir, state_dir, spawn, now, environ):
    if identity.nested(environ):
        return None
    try:
        projects = _projects(payload, environ)
        for project in projects:
            global_links.learn_aliases(project, repo_root, state_dir)
        report = global_links.sync(
            repo_root, skills_dir, state_dir, exclude=global_links.load_exclusions(repo_root),
        )
        warned = global_links.load_state(state_dir, WARNED)
        lines = (
            _lasting_conflicts(report, state_dir, warned)
            + _hidden_project_skills(projects, state_dir, warned)
            + _maintenance_news(state_dir, warned)
        )
        global_links.save_state(state_dir, WARNED, warned)
        _maybe_start_maintenance(state_dir, spawn, now)
        if lines:
            return {"systemMessage": " ".join(lines)}
    except Exception:
        _record_error(state_dir)
    return None


def _projects(payload, environ):
    candidates = {payload.get("cwd"), environ.get("CLAUDE_PROJECT_DIR")} - {None, ""}
    return sorted(path for path in candidates if os.path.isdir(path))


def _lasting_conflicts(report, state_dir, warned):
    previous = global_links.load_state(state_dir, LAST_SYNC)
    global_links.save_state(state_dir, LAST_SYNC, {"conflicts": report["conflicts"], "errors": report["errors"]})
    current = set(report["conflicts"])
    for key in [key for key in warned if key.startswith("conflict::") and key[10:] not in current]:
        del warned[key]
    lasting = sorted(current & set(previous.get("conflicts", [])))
    fresh = [name for name in lasting if "conflict::" + name not in warned]
    lines = []
    if fresh:
        lines.append(identity.say(CLAUDE_DIR,
            "~/.claude/skills already holds %s, which is not this repo's link, so "
            "that skill stays unlinked. Move it away, or list it in claude/global.json to stop "
            "linking it." % ", ".join(fresh)
        ))
        warned.update({"conflict::" + name: True for name in fresh})
    if report["errors"] and previous.get("errors"):
        lines.append(identity.say(CLAUDE_DIR, "linking skills keeps failing. Run claude/doctor.py for details."))
    return lines


def _hidden_project_skills(projects, state_dir, warned):
    """A personal link wins over a project skill with the same folder name."""
    owned = global_links.owned_links(state_dir)
    lines = []
    for project in projects:
        reflections = os.path.join(project, ".claude", "skills")
        if not os.path.isdir(reflections):
            continue
        for name in sorted(os.listdir(reflections)):
            if name not in owned:
                continue
            if os.path.realpath(os.path.join(reflections, name)) == os.path.realpath(owned[name]):
                continue
            key = "hidden::%s::%s" % (project, name)
            if key in warned:
                continue
            warned[key] = True
            lines.append(identity.say(CLAUDE_DIR,
                "your personal skill '%s' hides this project's own '%s' skill. "
                "List it in claude/global.json if the project's version should win." % (name, name)
            ))
    return lines


def _maintenance_news(state_dir, warned):
    """What the last background maintenance found that needs the owner, said once."""
    lines = []
    live = global_links.load_state(state_dir, LIVE_CHECK)
    if live and not live.get("passed") and "live::%s" % live.get("version") not in warned:
        warned["live::%s" % live.get("version")] = True
        lines.append(identity.say(CLAUDE_DIR,
            "after Claude Code updated to %s, some behaviour this setup relies on "
            "changed (live checks failed). Run claude/doctor.py." % live.get("version")
        ))
    diverged = global_links.load_state(state_dir, PULL).get("status") == "diverged"
    if not diverged:
        warned.pop("pull::diverged", None)
    elif "pull::diverged" not in warned:
        warned["pull::diverged"] = True
        lines.append(identity.say(CLAUDE_DIR,
            "this machine's copy of the repo has diverged from its remote, so it is no "
            "longer updated automatically. Reconcile it by hand."
        ))
    return lines


def _maybe_start_maintenance(state_dir, spawn, now):
    started = global_links.load_state(state_dir, MAINTENANCE_STAMP).get("started")
    if started is not None and now() - started < MAINTENANCE_INTERVAL_SECONDS:
        return
    global_links.save_state(state_dir, MAINTENANCE_STAMP, {"started": now()})
    spawn([sys.executable, MAINTENANCE])


def _spawn(command):
    if os.path.exists(command[-1]):
        subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )


def _record_error(state_dir):
    try:
        with open(os.path.join(state_dir, LAST_ERROR), "w", encoding="utf-8") as handle:
            handle.write(traceback.format_exc())
    except OSError:
        pass


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    environ = os.environ
    result = handle(
        payload if isinstance(payload, dict) else {},
        repo_root=REPO,
        skills_dir=identity.skills_dir(environ),
        state_dir=identity.state_dir(CLAUDE_DIR, environ),
        spawn=_spawn, now=time.time, environ=environ,
    )
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
