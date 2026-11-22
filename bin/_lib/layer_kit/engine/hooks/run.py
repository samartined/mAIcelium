#!/usr/bin/env python3
"""Run one of this repo's Claude Code hooks on behalf of its plugin.

The plugin's hooks.json calls `run.py <hook-name>` rather than each script, for one
reason: a machine may still register the same script by hand in a settings file, and
then the hook would run twice. When it finds such a registration, the dispatcher steps
aside and lets it run the script. Anything that goes wrong in here runs the script
anyway: a hook that runs twice is better than a hook that does not run.
"""

import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CLAUDE_DIR)

import identity  # noqa: E402

# The hooks this dispatcher may run, declared in hooks/registry.json.
HOOKS = identity.hooks(CLAUDE_DIR)


def settings_files(payload, home=None):
    """Settings files that could register a hook for this session."""
    home = home or os.path.expanduser("~")
    files = [os.path.join(home, ".claude", name) for name in ("settings.json", "settings.local.json")]
    for project in {os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")} - {None, ""}:
        files += [os.path.join(project, ".claude", name) for name in ("settings.json", "settings.local.json")]
    return files


def registered_elsewhere(script, files):
    target = os.path.realpath(script)
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                settings = json.load(handle)
        except FileNotFoundError:
            continue
        for groups in (settings.get("hooks") or {}).values():
            for group in groups or []:
                for hook in group.get("hooks") or []:
                    if any(_names(token, target) for token in _tokens(hook.get("command") or "")):
                        return True
    return False


def dispatch(script, payload_bytes, settings_files=()):
    try:
        if registered_elsewhere(script, settings_files):
            return 0, b"", b""
    except Exception:
        pass
    completed = subprocess.run([sys.executable, script], input=payload_bytes, capture_output=True)
    return completed.returncode, completed.stdout, completed.stderr


def _tokens(command):
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _names(token, target):
    path = os.path.expanduser(os.path.expandvars(token))
    return os.path.basename(path) == os.path.basename(target) and os.path.realpath(path) == target


def main(argv):
    file_name = HOOKS.get(argv[1] if len(argv) > 1 else "")
    if not file_name:
        return 0
    payload_bytes = sys.stdin.buffer.read()
    try:
        payload = json.loads(payload_bytes or b"{}")
    except ValueError:
        payload = {}
    code, out, err = dispatch(
        os.path.join(HERE, file_name), payload_bytes,
        settings_files(payload if isinstance(payload, dict) else {}),
    )
    sys.stdout.buffer.write(out)
    sys.stderr.buffer.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
