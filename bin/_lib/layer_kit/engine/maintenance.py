#!/usr/bin/env python3
"""Background maintenance of this repo on each machine.

The SessionStart hook starts it at most once every 30 minutes, detached from the
session. It:
1. fast-forwards the working tree when it is `main`, has no changes to tracked files
   and is behind its remote; anything else (local changes, another branch, diverged
   history, no network) is left exactly as it is;
2. syncs the personal skill links, so skills that just arrived are ready for the next
   session;
3. re-runs the live checks once each time Claude Code changes version, and keeps the
   result for the SessionStart hook to report.

Git never waits for a password, and a second copy steps aside while one runs.
"""

import contextlib
import fcntl
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import global_links  # noqa: E402
import identity  # noqa: E402

DEFAULT_BRANCH = "main"
GIT_TIMEOUT_SECONDS = 60
LIVE_TIMEOUT_SECONDS = 900
LOCK = "maintenance.lock"
PULL = "pull.json"
LIVE = "live_check.json"


def git_environment(environ):
    environment = dict(environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    ssh = environment.get("GIT_SSH_COMMAND") or "ssh"
    if "BatchMode" not in ssh:
        environment["GIT_SSH_COMMAND"] = ssh + " -o BatchMode=yes"
    return environment


@contextlib.contextmanager
def single_run(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, LOCK), "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def last_live_check(state_dir):
    return global_links.load_state(state_dir, LIVE)


def pull(repo_root, environ):
    """Fast-forward a clean main; return what happened in a few words."""
    environment = git_environment(environ)

    def git(*args):
        return subprocess.run(
            ["git", "-C", repo_root, *args], capture_output=True, text=True,
            env=environment, stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT_SECONDS,
        )

    if git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() != DEFAULT_BRANCH:
        return "skipped: not on main"
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        return "skipped: local changes"
    try:
        if git("fetch", "--quiet", "origin", DEFAULT_BRANCH).returncode != 0:
            return "offline"
    except subprocess.TimeoutExpired:
        return "offline"
    remote = "origin/" + DEFAULT_BRANCH
    if git("rev-parse", "HEAD").stdout == git("rev-parse", remote).stdout:
        return "current"
    if git("merge-base", "--is-ancestor", remote, "HEAD").returncode == 0:
        return "ahead"
    if git("merge-base", "--is-ancestor", "HEAD", remote).returncode != 0:
        return "diverged"
    if git("merge", "--ff-only", "--quiet", remote).returncode != 0:
        return "skipped: merge refused"
    return "updated"


def run(repo_root, skills_dir, state_dir, claude_version, run_live_checks, now=time.time, environ=None):
    environ = os.environ if environ is None else environ
    summary = {"pull": None, "live_check": None}
    with single_run(state_dir) as acquired:
        if not acquired:
            summary["pull"] = "busy"
            return summary
        try:
            summary["pull"] = pull(repo_root, environ)
        except Exception as error:
            summary["pull"] = "error: %s" % error
        global_links.save_state(state_dir, PULL, {"status": summary["pull"], "at": now()})
        global_links.sync(repo_root, skills_dir, state_dir, exclude=global_links.load_exclusions(repo_root))
        summary["live_check"] = _live_check(state_dir, claude_version, run_live_checks, now)
    return summary


def _live_check(state_dir, claude_version, run_live_checks, now):
    version = claude_version()
    if not version or last_live_check(state_dir).get("version") == version:
        return None
    passed, details = run_live_checks()
    record = {"version": version, "passed": passed, "details": details[-2000:], "at": now()}
    global_links.save_state(state_dir, LIVE, record)
    return record


def _installed_claude_version():
    try:
        completed = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    words = completed.stdout.split()
    return words[0] if completed.returncode == 0 and words else None


def _run_live_checks():
    try:
        completed = subprocess.run(
            [sys.executable, os.path.join(HERE, "tests", "test_live_platform.py")],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=LIVE_TIMEOUT_SECONDS,
            env=dict(os.environ, **{identity.NESTED_ENV: "1"}),
        )
    except subprocess.TimeoutExpired:
        return False, "live checks timed out"
    return completed.returncode == 0, completed.stdout + completed.stderr


def main():
    run(
        REPO,
        identity.skills_dir(os.environ),
        identity.state_dir(HERE, os.environ),
        claude_version=_installed_claude_version,
        run_live_checks=_run_live_checks,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
