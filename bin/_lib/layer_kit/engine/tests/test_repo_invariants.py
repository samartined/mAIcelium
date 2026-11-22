#!/usr/bin/env python3
"""Repo invariants the global links rely on. Run: python3 claude/tests/test_repo_invariants.py

Why this file exists: each skill becomes a link named after its folder, and Claude
Code merges same-named skills. A skill whose `name:` differs from its folder, or two
skills with the same folder name, would load under the wrong name or hide each other
in every session. The plugin must load nothing but hooks, and every hook must be
declared once in hooks/registry.json, wired in hooks/hooks.json and present on disk.
"""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PLUGIN_ROOT = os.path.join(REPO, "claude")
HOOKS_DIR = os.path.join(PLUGIN_ROOT, "hooks")
NAME_LINE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
# Anything here would make Claude Code load more than hooks from the plugin, and a
# plugin skill never merges with the same skill reflected by a workspace.
LOADABLE_COMPONENTS = ("skills", "agents", "commands", "output-styles", ".mcp.json", ".lsp.json", "settings.json")


def skill_files():
    for folder, _, files in os.walk(os.path.join(REPO, "skills")):
        if "SKILL.md" in files:
            yield folder, os.path.join(folder, "SKILL.md")


def read_json(*parts):
    with open(os.path.join(PLUGIN_ROOT, *parts), encoding="utf-8") as handle:
        return json.load(handle)


def registry():
    return read_json("hooks", "registry.json")


def dispatched_names():
    """Hook names the plugin sends through run.py, over every event."""
    names = set()
    for groups in read_json("hooks", "hooks.json")["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                words = hook["command"].split()
                if any(word.strip('"').endswith("/hooks/run.py") for word in words):
                    names.add(words[-1])
    return names


class SkillNames(unittest.TestCase):
    def test_every_skill_name_matches_its_folder(self):
        mismatched = []
        for folder, path in skill_files():
            with open(path, encoding="utf-8") as handle:
                match = NAME_LINE.search(handle.read())
            declared = match.group(1).strip("'\"") if match else None
            if declared != os.path.basename(folder):
                mismatched.append("%s declares %r" % (os.path.relpath(folder, REPO), declared))
        self.assertEqual(mismatched, [])

    def test_no_two_skills_share_a_folder_name(self):
        seen = {}
        for folder, _ in skill_files():
            seen.setdefault(os.path.basename(folder), []).append(os.path.relpath(folder, REPO))
        self.assertEqual({name: places for name, places in seen.items() if len(places) > 1}, {})


class PluginShape(unittest.TestCase):
    def test_the_manifest_names_the_plugin(self):
        self.assertTrue(read_json(".claude-plugin", "plugin.json").get("name"))

    def test_the_plugin_root_holds_nothing_loadable_but_hooks(self):
        present = [name for name in LOADABLE_COMPONENTS if os.path.exists(os.path.join(PLUGIN_ROOT, name))]
        self.assertEqual(present, [])


class HookRegistry(unittest.TestCase):
    def test_every_registered_hook_is_wired_and_every_wired_hook_is_registered(self):
        self.assertEqual(dispatched_names(), set(registry()))

    def test_every_hook_script_on_disk_is_registered_and_every_registered_script_exists(self):
        on_disk = {
            name for name in os.listdir(HOOKS_DIR)
            if name.endswith(".py") and not name.startswith("test_") and name != "run.py"
        }
        declared = {entry["script"] for entry in registry().values()}
        self.assertEqual(on_disk - declared, set(), "scripts no hook declares")
        self.assertEqual(declared - on_disk, set(), "declared scripts that do not exist")

    def test_every_repo_hook_names_its_test_skills_rules_and_needs(self):
        problems = []
        hooks = registry()
        for name, entry in hooks.items():
            if entry.get("origin") not in ("engine", "repo"):
                problems.append("%s: origin must be engine or repo" % name)
            if entry.get("origin") != "repo":
                continue
            if not os.path.isfile(os.path.join(HOOKS_DIR, entry.get("test") or "missing")):
                problems.append("%s: its test file is missing" % name)
            for skill in entry.get("skills", []):
                if not os.path.isfile(os.path.join(REPO, "skills", skill, "SKILL.md")):
                    problems.append("%s: skill %s does not exist" % (name, skill))
            for rule in entry.get("rules", []):
                if not os.path.isfile(os.path.join(REPO, "rules", rule)):
                    problems.append("%s: rule %s does not exist" % (name, rule))
            for needed in entry.get("needs", []):
                if needed not in hooks:
                    problems.append("%s: needs unknown hook %s" % (name, needed))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
