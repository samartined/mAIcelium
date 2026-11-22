#!/usr/bin/env python3
"""SessionStart hook tests. Run: python3 claude/tests/test_session_start.py

Why this file exists: this hook runs at the start of every session on the machine, so
it must be quick, silent when all is well, and say one line only when the owner has to act.
It keeps the skill links in sync, learns the names a workspace uses, warns once when a
personal skill hides a different project skill, and starts the background maintenance
no more than once per interval. It must never break a session start.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))

import session_start  # noqa: E402


def write_skill(folder):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: %s\ndescription: d\n---\nbody\n" % os.path.basename(folder))


class StartCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.root = os.path.realpath(directory)
        self.repo = os.path.join(self.root, "repo")
        self.skills_dir = os.path.join(self.root, "home", ".claude", "skills")
        self.state = os.path.join(self.root, "state")
        self.project = os.path.join(self.root, "project")
        os.makedirs(self.skills_dir)
        os.makedirs(self.project)
        write_skill(os.path.join(self.repo, "skills", "_common", "alpha"))
        write_skill(os.path.join(self.repo, "skills", "_domains", "dom", "child"))
        self.spawned = []
        self.clock = [1000.0]

    def start(self, environ=None, cwd=None):
        return session_start.handle(
            {"hook_event_name": "SessionStart", "source": "startup", "cwd": cwd or self.project},
            repo_root=self.repo, skills_dir=self.skills_dir, state_dir=self.state,
            spawn=self.spawned.append, now=lambda: self.clock[0], environ=environ or {},
        )

    def linked(self):
        return sorted(name for name in os.listdir(self.skills_dir) if os.path.islink(os.path.join(self.skills_dir, name)))


class Quiet(StartCase):
    def test_links_the_skills_and_says_nothing(self):
        self.assertIsNone(self.start())
        self.assertEqual(self.linked(), ["alpha", "child"])

    def test_stays_out_of_nested_test_sessions(self):
        self.assertIsNone(self.start(environ={"SKILLS_REPO_NESTED": "1"}))
        self.assertEqual((self.linked(), self.spawned), ([], []))

    def test_learns_the_workspace_names_before_linking(self):
        reflections = os.path.join(self.project, ".claude", "skills")
        os.makedirs(reflections)
        os.symlink(os.path.join(self.repo, "skills", "_domains", "dom", "child"), os.path.join(reflections, "dom--child"))
        self.start()
        self.assertEqual(self.linked(), ["alpha", "dom--child"])

    def test_never_breaks_a_session_start(self):
        with open(self.state, "w") as handle:
            handle.write("a file where a folder should be")
        self.assertIsNone(self.start())


class SpeaksWhenNeeded(StartCase):
    def test_a_conflict_is_mentioned_once_it_persists(self):
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.join(self.skills_dir, "alpha"))
        self.assertIsNone(self.start())
        message = self.start()["systemMessage"]
        self.assertIn("alpha", message)

    def test_warns_once_when_a_personal_skill_hides_a_project_skill(self):
        project_skill = os.path.join(self.project, ".claude", "skills", "alpha")
        write_skill(project_skill)
        self.assertIn("alpha", self.start()["systemMessage"])
        self.assertIsNone(self.start())


class ReportsMaintenance(StartCase):
    def remember(self, name, data):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, name), "w") as handle:
            json.dump(data, handle)

    def test_failed_live_checks_after_an_update_are_mentioned_once(self):
        self.remember("live_check.json", {"version": "9.9.9", "passed": False, "details": "L1 failed"})
        self.assertIn("9.9.9", self.start()["systemMessage"])
        self.assertIsNone(self.start())

    def test_passing_live_checks_say_nothing(self):
        self.remember("live_check.json", {"version": "9.9.9", "passed": True, "details": "ok"})
        self.assertIsNone(self.start())

    def test_a_diverged_repo_is_mentioned_once(self):
        self.remember("pull.json", {"status": "diverged"})
        self.assertIn("diverged", self.start()["systemMessage"])
        self.assertIsNone(self.start())


class Maintenance(StartCase):
    def test_started_at_most_once_per_interval(self):
        self.start()
        self.start()
        self.clock[0] += session_start.MAINTENANCE_INTERVAL_SECONDS + 1
        self.start()
        self.assertEqual(len(self.spawned), 2)


class Speed(StartCase):
    def test_thirty_skills_take_under_three_hundred_milliseconds(self):
        for index in range(30):
            write_skill(os.path.join(self.repo, "skills", "_common", "skill-%02d" % index))
        began = time.monotonic()
        self.start()
        self.start()
        elapsed = (time.monotonic() - began) / 2
        self.assertEqual(len(self.linked()), 32)
        self.assertLess(elapsed, 0.3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
