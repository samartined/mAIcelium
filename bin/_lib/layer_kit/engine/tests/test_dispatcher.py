#!/usr/bin/env python3
"""Dispatcher tests. Run: python3 claude/tests/test_dispatcher.py

Why this file exists: the plugin runs every hook of this repo through one dispatcher.
A machine may still have the same hook registered by hand in a settings file, and then
the hook would run twice. The dispatcher must step aside in that case and only then; it
must pass the hook's input, output and exit code through untouched; and a failure of
its own must never stop the real hook from running.
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
sys.path.insert(0, os.path.join(CLAUDE_DIR, "hooks"))

import run  # noqa: E402

FAKE_HOOK = """#!/usr/bin/env python3
import json, sys
payload = json.load(sys.stdin)
with open(%r, "a") as marker:
    marker.write("ran\\n")
print(json.dumps({"seen": payload.get("tool_name")}))
sys.stderr.write("note\\n")
sys.exit(%d)
"""


class DispatcherCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.root = os.path.realpath(directory)
        self.hooks_dir = os.path.join(self.root, "repo", "claude", "hooks")
        os.makedirs(self.hooks_dir)
        shutil.copy(os.path.join(CLAUDE_DIR, "identity.py"), os.path.dirname(self.hooks_dir))
        with open(os.path.join(self.hooks_dir, "registry.json"), "w") as handle:
            json.dump({"guard": {"script": "guard.py", "origin": "repo"}}, handle)
        self.marker = os.path.join(self.root, "marker")
        self.script = self.fake_hook("guard.py", exit_code=2)
        self.user_settings = os.path.join(self.root, "home", ".claude", "settings.json")
        self.project = os.path.join(self.root, "project")
        os.makedirs(os.path.join(self.project, ".claude"))

    def fake_hook(self, file_name, exit_code=0):
        path = os.path.join(self.hooks_dir, file_name)
        with open(path, "w") as handle:
            handle.write(FAKE_HOOK % (self.marker, exit_code))
        os.chmod(path, 0o755)
        return path

    def register(self, settings_path, command):
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        hooks = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}]}}
        with open(settings_path, "w") as handle:
            json.dump(hooks, handle)

    def dispatch(self, payload=None):
        payload = payload or {"tool_name": "Bash", "cwd": self.project}
        return run.dispatch(
            self.script, json.dumps(payload).encode(),
            settings_files=run.settings_files(payload, home=os.path.join(self.root, "home")),
        )

    def ran(self):
        return os.path.exists(self.marker)


class PassThrough(DispatcherCase):
    def test_input_output_and_exit_code_reach_through(self):
        code, out, err = self.dispatch()
        self.assertEqual((code, json.loads(out), err), (2, {"seen": "Bash"}, b"note\n"))


class StepsAside(DispatcherCase):
    def test_when_user_settings_register_the_same_script(self):
        self.register(self.user_settings, self.script)
        self.assertEqual(self.dispatch(), (0, b"", b""))
        self.assertFalse(self.ran())

    def test_when_project_settings_register_it_with_an_interpreter(self):
        self.register(os.path.join(self.project, ".claude", "settings.local.json"), "python3 '%s'" % self.script)
        self.assertEqual(self.dispatch(), (0, b"", b""))
        self.assertFalse(self.ran())

    def test_not_for_another_script_with_the_same_file_name(self):
        other = os.path.join(self.root, "elsewhere", "guard.py")
        os.makedirs(os.path.dirname(other))
        shutil.copy(self.script, other)
        self.register(self.user_settings, other)
        self.dispatch()
        self.assertTrue(self.ran())


class NeverBlocksTheHook(DispatcherCase):
    def test_unreadable_settings_still_run_the_hook(self):
        os.makedirs(os.path.dirname(self.user_settings))
        with open(self.user_settings, "w") as handle:
            handle.write("{not json")
        self.dispatch()
        self.assertTrue(self.ran())


class CommandLine(DispatcherCase):
    """The plugin calls run.py through a link; it must still find the repo's scripts."""

    def test_through_a_linked_plugin_root(self):
        shutil.copy(os.path.join(CLAUDE_DIR, "hooks", "run.py"), self.hooks_dir)
        link = os.path.join(self.root, "home", ".claude", "skills", "acme-skills")
        os.makedirs(os.path.dirname(link))
        os.symlink(os.path.join(self.root, "repo", "claude"), link)
        payload = json.dumps({"tool_name": "Bash", "cwd": self.project}).encode()
        completed = subprocess.run(
            [sys.executable, os.path.join(link, "hooks", "run.py"), "guard"],
            input=payload, capture_output=True, env=dict(os.environ, HOME=os.path.join(self.root, "home")),
        )
        self.assertEqual((completed.returncode, json.loads(completed.stdout)), (2, {"seen": "Bash"}))

    def test_a_known_name_runs_its_hook_and_an_unknown_one_does_nothing(self):
        shutil.copy(os.path.join(CLAUDE_DIR, "hooks", "run.py"), self.hooks_dir)
        home = dict(os.environ, HOME=os.path.join(self.root, "home"))

        def call(name):
            return subprocess.run(
                [sys.executable, os.path.join(self.hooks_dir, "run.py"), name],
                input=b'{"tool_name": "Bash"}', capture_output=True, env=home,
            )

        call("guard")
        self.assertTrue(self.ran())
        os.remove(self.marker)
        completed = call("no-such-hook")
        self.assertEqual((completed.returncode, completed.stdout), (0, b""))
        self.assertFalse(self.ran())


if __name__ == "__main__":
    unittest.main(verbosity=2)
