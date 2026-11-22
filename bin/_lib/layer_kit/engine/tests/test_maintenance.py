#!/usr/bin/env python3
"""Background maintenance tests. Run: python3 claude/tests/test_maintenance.py

Why this file exists: maintenance runs unattended, in the background, on every machine.
It may move the repo's working tree forward, so it must only ever fast-forward a clean
`main` and leave anything else exactly as it was; it must never wait for a password;
two copies must never run at once; and after an update the links must be ready before
the next session. When Claude Code changes version it re-runs the live checks, once.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maintenance  # noqa: E402


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def add_skill(work, name):
    folder = os.path.join(work, "skills", "_common", name)
    os.makedirs(folder)
    with open(os.path.join(folder, "SKILL.md"), "w") as handle:
        handle.write("---\nname: %s\ndescription: d\n---\nbody\n" % name)
    git(work, "add", "-A")
    git(work, "commit", "-qm", "add " + name)


class MaintenanceCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.root = os.path.realpath(directory)
        self.remote = os.path.join(self.root, "remote.git")
        self.upstream = os.path.join(self.root, "upstream")
        self.clone = os.path.join(self.root, "clone")
        self.skills_dir = os.path.join(self.root, "home", ".claude", "skills")
        self.state = os.path.join(self.root, "state")
        git(self.root, "init", "-q", "--bare", "-b", "main", self.remote)
        git(self.root, "clone", "-q", self.remote, self.upstream)
        git(self.upstream, "checkout", "-qb", "main")
        add_skill(self.upstream, "alpha")
        git(self.upstream, "push", "-q", "origin", "main")
        git(self.root, "clone", "-q", self.remote, self.clone)
        self.live_runs = []
        self.version = ["2.1.329"]

    def run_maintenance(self):
        return maintenance.run(
            self.clone, self.skills_dir, self.state,
            claude_version=lambda: self.version[0],
            run_live_checks=lambda: self.live_runs.append(self.version[0]) or (True, "ok"),
        )

    def remote_moves_ahead(self):
        add_skill(self.upstream, "beta")
        git(self.upstream, "push", "-q", "origin", "main")

    def head(self, repo):
        return git(repo, "rev-parse", "HEAD")


class FastForward(MaintenanceCase):
    def test_a_clean_main_behind_its_remote_moves_forward(self):
        self.remote_moves_ahead()
        self.assertEqual(self.run_maintenance()["pull"], "updated")
        self.assertEqual(self.head(self.clone), self.head(self.upstream))

    def test_links_are_ready_for_the_next_session(self):
        self.remote_moves_ahead()
        self.run_maintenance()
        self.assertTrue(os.path.islink(os.path.join(self.skills_dir, "beta")))

    def test_an_up_to_date_clone_is_current(self):
        self.assertEqual(self.run_maintenance()["pull"], "current")


class LeavesItAlone(MaintenanceCase):
    def test_local_changes(self):
        self.remote_moves_ahead()
        before = self.head(self.clone)
        with open(os.path.join(self.clone, "skills", "_common", "alpha", "SKILL.md"), "a") as handle:
            handle.write("work in progress\n")
        self.assertEqual(self.run_maintenance()["pull"], "skipped: local changes")
        self.assertEqual(self.head(self.clone), before)

    def test_untracked_files_such_as_caches_do_not_block_it(self):
        self.remote_moves_ahead()
        os.makedirs(os.path.join(self.clone, "claude", "__pycache__"))
        with open(os.path.join(self.clone, "claude", "__pycache__", "x.pyc"), "w") as handle:
            handle.write("cache")
        self.assertEqual(self.run_maintenance()["pull"], "updated")

    def test_another_branch(self):
        self.remote_moves_ahead()
        git(self.clone, "checkout", "-qb", "experiment")
        before = self.head(self.clone)
        self.assertEqual(self.run_maintenance()["pull"], "skipped: not on main")
        self.assertEqual(self.head(self.clone), before)

    def test_diverged_history(self):
        self.remote_moves_ahead()
        add_skill(self.clone, "local-only")
        before = self.head(self.clone)
        self.assertEqual(self.run_maintenance()["pull"], "diverged")
        self.assertEqual(self.head(self.clone), before)

    def test_unreachable_remote(self):
        shutil.rmtree(self.remote)
        self.assertEqual(self.run_maintenance()["pull"], "offline")


class Unattended(MaintenanceCase):
    def test_git_never_waits_for_a_password(self):
        environment = maintenance.git_environment({})
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertIn("BatchMode=yes", environment["GIT_SSH_COMMAND"])

    def test_a_second_copy_steps_aside_while_one_runs(self):
        with maintenance.single_run(self.state) as first:
            with maintenance.single_run(self.state) as second:
                self.assertEqual((first, second), (True, False))


class LiveChecks(MaintenanceCase):
    def test_rerun_once_when_claude_code_changes_version(self):
        self.run_maintenance()
        self.run_maintenance()
        self.version[0] = "2.1.330"
        self.run_maintenance()
        self.assertEqual(self.live_runs, ["2.1.329", "2.1.330"])

    def test_the_result_is_kept_for_the_session_start_hook(self):
        self.run_maintenance()
        self.assertEqual(maintenance.last_live_check(self.state)["version"], "2.1.329")


if __name__ == "__main__":
    unittest.main(verbosity=2)
