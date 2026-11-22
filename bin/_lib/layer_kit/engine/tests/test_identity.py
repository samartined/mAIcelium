#!/usr/bin/env python3
"""Identity tests. Run: python3 claude/tests/test_identity.py

Why this file exists: the engine is the same file in every skills repo built from it,
so nothing that names one repo may be written in its code. Each repo's identity lives in
its plugin manifest and its global.json, and two repos on one machine must never share a
plugin link, a state folder or a hook list.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CLAUDE_DIR)

import identity  # noqa: E402


class IdentityCase(unittest.TestCase):
    def setUp(self):
        self.claude = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.claude, True)
        self.write(".claude-plugin/plugin.json", {"name": "acme-skills", "author": {"name": "Ada"}})

    def write(self, relative, data):
        path = os.path.join(self.claude, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)


class FromTheManifest(IdentityCase):
    def test_the_plugin_name_and_owner(self):
        self.assertEqual((identity.name(self.claude), identity.owner(self.claude)), ("acme-skills", "Ada"))

    def test_the_messages_carry_the_plugin_name(self):
        self.assertTrue(identity.say(self.claude, "hello").startswith("acme-skills: "))


class StateFolder(IdentityCase):
    def test_defaults_to_the_plugin_name_under_the_state_home(self):
        environ = {"XDG_STATE_HOME": "/state"}
        self.assertEqual(identity.state_dir(self.claude, environ), os.path.join("/state", "acme-skills"))

    def test_global_json_can_keep_an_older_folder_name(self):
        self.write("global.json", {"state_dir": "older-name"})
        environ = {"XDG_STATE_HOME": "/state"}
        self.assertEqual(identity.state_dir(self.claude, environ), os.path.join("/state", "older-name"))

    def test_the_environment_wins(self):
        environ = {"XDG_STATE_HOME": "/state", identity.STATE_DIR_ENV: "/elsewhere"}
        self.assertEqual(identity.state_dir(self.claude, environ), "/elsewhere")


class Switches(unittest.TestCase):
    def test_nested_sessions_are_recognised(self):
        self.assertTrue(identity.nested({identity.NESTED_ENV: "1"}))
        self.assertFalse(identity.nested({}))

    def test_the_skills_folder_can_be_moved_for_tests(self):
        self.assertEqual(identity.skills_dir({identity.SKILLS_DIR_ENV: "/x"}), "/x")
        self.assertTrue(identity.skills_dir({}).endswith(os.path.join(".claude", "skills")))


class HookRegistry(IdentityCase):
    def test_the_dispatcher_reads_its_hooks_from_the_registry(self):
        self.write("hooks/registry.json", {
            "session-start": {"script": "session_start.py", "origin": "engine"},
            "guard": {"script": "guard.py", "origin": "repo"},
        })
        self.assertEqual(identity.hooks(self.claude), {"session-start": "session_start.py", "guard": "guard.py"})

    def test_a_missing_registry_means_no_hooks(self):
        self.assertEqual(identity.hooks(self.claude), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
