"""Who this skills repo is, read from its own files.

The engine is the same code in every skills repo built from the mAIcelium layer kit, so
nothing here names a repo. Each repo says who it is in two files it owns:
- claude/.claude-plugin/plugin.json: `name` (the plugin, its link under ~/.claude/skills
  and the prefix of every message) and `author.name` (the owner);
- claude/global.json: optional `state_dir`, the folder name of the per-machine state when
  it must differ from the plugin name, and `exclude`, skills never linked globally;
- claude/hooks/registry.json: the hooks the dispatcher may run.
"""

import json
import os

STATE_DIR_ENV = "SKILLS_REPO_STATE_DIR"
NESTED_ENV = "SKILLS_REPO_NESTED"
SKILLS_DIR_ENV = "SKILLS_REPO_SKILLS_DIR"


def name(claude_dir):
    return _manifest(claude_dir).get("name") or "skills-repo"


def owner(claude_dir):
    return (_manifest(claude_dir).get("author") or {}).get("name") or ""


def say(claude_dir, text):
    """One message for the owner, prefixed with the plugin name."""
    return "%s: %s" % (name(claude_dir), text)


def state_dir(claude_dir, environ):
    """Where the engine keeps its manifest, aliases and status: per machine, outside the repo."""
    if environ.get(STATE_DIR_ENV):
        return environ[STATE_DIR_ENV]
    base = environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, _read(os.path.join(claude_dir, "global.json")).get("state_dir") or name(claude_dir))


def skills_dir(environ):
    return environ.get(SKILLS_DIR_ENV) or os.path.join(os.path.expanduser("~"), ".claude", "skills")


def nested(environ):
    """True inside the throwaway sessions the live checks start: the engine stays quiet there."""
    return environ.get(NESTED_ENV) == "1"


def hooks(claude_dir):
    """Hook name -> script file name, from claude/hooks/registry.json."""
    registry = _read(os.path.join(claude_dir, "hooks", "registry.json"))
    return {hook: entry["script"] for hook, entry in registry.items()}


def _manifest(claude_dir):
    return _read(os.path.join(claude_dir, ".claude-plugin", "plugin.json"))


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return {}
