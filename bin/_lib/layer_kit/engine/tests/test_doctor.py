#!/usr/bin/env python3
"""Doctor tests. Run: python3 claude/tests/test_doctor.py

Why this file exists: the doctor is what the owner runs when a one-line warning asks for it,
and the one command that sets a new machine up. It must tell the truth about the
machine, fix only what belongs to this repo (the plugin link, the skill links, manual
registrations of the hooks the plugin now delivers), keep a backup of any settings file
it edits, and undo everything on request without touching anything else.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CLAUDE_DIR)

import doctor  # noqa: E402


def write_skill(folder):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: %s\ndescription: d\n---\nbody\n" % os.path.basename(folder))


class DoctorCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.root = os.path.realpath(directory)
        self.repo = os.path.join(self.root, "repo")
        self.home = os.path.join(self.root, "home")
        self.state = os.path.join(self.root, "state")
        self.skills_dir = os.path.join(self.home, ".claude", "skills")
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        write_skill(os.path.join(self.repo, "skills", "_common", "alpha"))
        write_skill(os.path.join(self.repo, "skills", "_common", "beta"))
        hooks = os.path.join(self.repo, "claude", "hooks")
        os.makedirs(hooks)
        self.hook_script = os.path.join(hooks, "guard.py")
        with open(self.hook_script, "w") as handle:
            handle.write("# hook\n")
        with open(os.path.join(hooks, "registry.json"), "w") as handle:
            json.dump({"guard": {"script": "guard.py", "origin": "repo"}}, handle)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        os.makedirs(self.skills_dir)

    def write_settings(self, hooks):
        settings = {"model": "opus", "hooks": hooks}
        with open(self.settings, "w") as handle:
            json.dump(settings, handle)

    def legacy_group(self):
        return {"matcher": "Read|Edit", "hooks": [{"type": "command", "command": self.hook_script}]}

    def other_group(self):
        return {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/other-hook"}]}

    def diagnose(self):
        return doctor.diagnose(self.repo, self.home, self.state)

    def fix(self):
        return doctor.fix(self.repo, self.home, self.state)

    def plugin_link(self):
        return os.path.join(self.skills_dir, doctor.PLUGIN_LINK)


class Diagnose(DoctorCase):
    def test_a_fixed_machine_is_healthy(self):
        self.fix()
        diagnosis = self.diagnose()
        self.assertTrue(doctor.healthy(diagnosis), doctor.format_report(diagnosis))

    def test_a_missing_plugin_link_is_reported(self):
        self.assertEqual(self.diagnose()["plugin"], "missing")

    def test_missing_skill_links_are_reported(self):
        self.fix()
        os.remove(os.path.join(self.skills_dir, "beta"))
        self.assertEqual(self.diagnose()["missing_links"], ["beta"])

    def test_a_manual_registration_of_a_delivered_hook_is_reported(self):
        self.write_settings({"PreToolUse": [self.legacy_group()]})
        self.assertEqual(self.diagnose()["legacy"], [self.hook_script])

    def test_a_live_tree_off_main_is_reported(self):
        self.fix()
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", "experiment"], check=True)
        diagnosis = self.diagnose()
        self.assertEqual(diagnosis["branch"], "experiment")
        self.assertFalse(doctor.healthy(diagnosis))


class Fix(DoctorCase):
    def test_links_the_plugin_and_the_skills(self):
        self.fix()
        self.assertEqual(os.path.realpath(self.plugin_link()), os.path.join(self.repo, "claude"))
        self.assertTrue(os.path.islink(os.path.join(self.skills_dir, "alpha")))

    def test_removes_only_manual_registrations_of_delivered_hooks_and_keeps_a_backup(self):
        self.write_settings({"PreToolUse": [self.legacy_group(), self.other_group()], "PostToolUse": [self.legacy_group()]})
        self.fix()
        with open(self.settings) as handle:
            settings = json.load(handle)
        self.assertEqual(settings, {"model": "opus", "hooks": {"PreToolUse": [self.other_group()]}})
        backups = [name for name in os.listdir(os.path.dirname(self.settings)) if name.startswith("settings.json.bak-")]
        self.assertEqual(len(backups), 1)

    def test_never_replaces_a_foreign_entry_named_like_the_plugin_link(self):
        os.makedirs(self.plugin_link())
        self.fix()
        self.assertFalse(os.path.islink(self.plugin_link()))
        self.assertEqual(self.diagnose()["plugin"], "foreign")


class HardRulesImport(DoctorCase):
    """The hard rules reach a session only through an import in ~/.claude/CLAUDE.md.
    A machine without that file loaded none of them, and nothing said so."""

    def claude_md(self):
        return os.path.join(self.home, ".claude", "CLAUDE.md")

    def write_claude_md(self, text):
        with open(self.claude_md(), "w", encoding="utf-8") as handle:
            handle.write(text)

    def read_claude_md(self):
        with open(self.claude_md(), encoding="utf-8") as handle:
            return handle.read()

    def import_line(self):
        return "@" + os.path.join(self.repo, "claude", "hard-rules.md")

    def test_a_machine_without_the_file_needs_attention(self):
        diagnosis = self.diagnose()
        self.assertEqual(diagnosis["hard_rules"], "missing")
        self.assertFalse(doctor.healthy(diagnosis))
        self.assertIn("hard rules import: missing", doctor.format_report(diagnosis))

    def test_a_file_without_the_import_needs_attention(self):
        self.write_claude_md("# my notes\n")
        self.assertEqual(self.diagnose()["hard_rules"], "missing")

    def test_an_import_written_from_home_counts(self):
        self.write_claude_md("# notes\n@~/%s\n" % os.path.relpath(os.path.join(self.repo, "claude", "hard-rules.md"), self.home))
        self.assertEqual(self.diagnose()["hard_rules"], "ok")

    def test_fix_creates_the_file_with_the_import(self):
        self.fix()
        self.assertEqual(self.diagnose()["hard_rules"], "ok")
        self.assertIn("hard-rules.md", self.read_claude_md())

    def test_fix_appends_to_an_existing_file_and_keeps_a_backup(self):
        self.write_claude_md("# my notes\n")
        self.fix()
        self.assertTrue(self.read_claude_md().startswith("# my notes\n"))
        self.assertEqual(self.diagnose()["hard_rules"], "ok")
        backups = [name for name in os.listdir(os.path.dirname(self.claude_md())) if name.startswith("CLAUDE.md.bak-")]
        self.assertEqual(len(backups), 1)

    def test_uninstall_removes_only_the_import(self):
        self.write_claude_md("# my notes\n")
        self.fix()
        doctor.uninstall(self.repo, self.home, self.state)
        self.assertEqual(self.read_claude_md(), "# my notes\n")


class Uninstall(DoctorCase):
    def test_leaves_the_machine_as_it_was_except_for_foreign_entries(self):
        os.makedirs(os.path.join(self.skills_dir, "synced"))
        self.write_settings({"PreToolUse": [self.other_group()]})
        self.fix()
        self.assertTrue(os.path.islink(self.plugin_link()) and os.path.islink(os.path.join(self.skills_dir, "alpha")))
        doctor.uninstall(self.repo, self.home, self.state)
        self.assertEqual(sorted(os.listdir(self.skills_dir)), ["synced"])
        self.assertFalse(os.path.exists(self.state))
        with open(self.settings) as handle:
            self.assertEqual(json.load(handle)["hooks"], {"PreToolUse": [self.other_group()]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
