#!/usr/bin/env python3
"""Link engine tests. Run: python3 claude/tests/test_global_links.py

Why this file exists: the engine writes into ~/.claude/skills/, a folder shared by
every session on the machine and by things that are not ours (org-synced skills,
skills the owner made by hand, the plugin link). It must add and remove exactly its own
links, follow the repo as skills come, go, move or get renamed, and survive many
sessions starting at once. Every case below is one of those promises.
"""

import json
import multiprocessing
import os
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import global_links  # noqa: E402


def write_skill(folder):
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(folder)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: %s\ndescription: d\n---\nbody\n" % name)


class EngineCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.root = os.path.realpath(directory)
        self.repo = os.path.join(self.root, "repo")
        self.skills_dir = os.path.join(self.root, "home", ".claude", "skills")
        self.state = os.path.join(self.root, "state")
        os.makedirs(self.skills_dir)
        for relative in ("_common/alpha", "_domains/dom", "_domains/dom/child",
                         "_domains/plain/leaf", "_common/excluded"):
            write_skill(os.path.join(self.repo, "skills", relative))
        os.makedirs(os.path.join(self.repo, "skills", "_common", "alpha", "references"))

    def folder(self, relative):
        return os.path.join(self.repo, "skills", relative)

    def link(self, name):
        return os.path.join(self.skills_dir, name)

    def sync(self, exclude=("excluded",)):
        return global_links.sync(self.repo, self.skills_dir, self.state, exclude=exclude)

    def linked(self):
        return {
            name: os.readlink(self.link(name))
            for name in os.listdir(self.skills_dir)
            if os.path.islink(self.link(name))
        }


class Discovery(EngineCase):
    def test_every_folder_with_a_skill_file_is_a_skill_named_after_its_folder(self):
        found = global_links.discover_skills(self.repo, exclude=("excluded",))
        self.assertEqual(found, {
            "alpha": self.folder("_common/alpha"),
            "dom": self.folder("_domains/dom"),
            "child": self.folder("_domains/dom/child"),
            "leaf": self.folder("_domains/plain/leaf"),
        })

    def test_exclusions_come_from_the_repo_config(self):
        os.makedirs(os.path.join(self.repo, "claude"))
        with open(os.path.join(self.repo, "claude", "global.json"), "w") as handle:
            json.dump({"exclude": ["excluded", "leaf"]}, handle)
        self.assertEqual(global_links.load_exclusions(self.repo), ["excluded", "leaf"])

    def test_no_config_means_no_exclusions(self):
        self.assertEqual(global_links.load_exclusions(self.repo), [])


class Sync(EngineCase):
    def test_creates_one_link_per_skill(self):
        self.sync()
        self.assertEqual(self.linked(), {
            "alpha": self.folder("_common/alpha"),
            "dom": self.folder("_domains/dom"),
            "child": self.folder("_domains/dom/child"),
            "leaf": self.folder("_domains/plain/leaf"),
        })

    def test_creates_the_personal_skills_folder_on_a_fresh_machine(self):
        shutil.rmtree(self.skills_dir)
        self.sync()
        self.assertEqual(sorted(self.linked()), ["alpha", "child", "dom", "leaf"])

    def test_a_second_run_changes_nothing(self):
        self.sync()
        report = self.sync()
        self.assertEqual((report["created"], report["updated"], report["removed"]), ([], [], []))

    def test_removes_its_link_when_the_skill_leaves_the_repo(self):
        self.sync()
        shutil.rmtree(self.folder("_domains/plain/leaf"))
        report = self.sync()
        self.assertNotIn("leaf", self.linked())
        self.assertEqual(report["removed"], ["leaf"])

    def test_follows_a_skill_that_moves_inside_the_repo(self):
        self.sync()
        shutil.move(self.folder("_domains/plain/leaf"), self.folder("_common/leaf"))
        self.sync()
        self.assertEqual(self.linked()["leaf"], self.folder("_common/leaf"))

    def test_never_touches_a_foreign_link_with_the_same_name(self):
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, self.link("alpha"))
        report = self.sync()
        self.assertEqual(os.readlink(self.link("alpha")), elsewhere)
        self.assertEqual(report["conflicts"], ["alpha"])

    def test_never_touches_a_real_folder_with_the_same_name(self):
        os.makedirs(self.link("dom"))
        report = self.sync()
        self.assertTrue(os.path.isdir(self.link("dom")) and not os.path.islink(self.link("dom")))
        self.assertEqual(report["conflicts"], ["dom"])

    def test_leaves_unrelated_entries_alone(self):
        os.makedirs(os.path.join(self.skills_dir, "synced", "org"))
        os.symlink(self.root, self.link("plugin-link"))
        self.sync()
        shutil.rmtree(self.folder("_common/alpha"))
        report = self.sync()
        self.assertEqual(report["removed"], ["alpha"])
        self.assertTrue(os.path.isdir(os.path.join(self.skills_dir, "synced", "org")))
        self.assertEqual(os.readlink(self.link("plugin-link")), self.root)

    def test_a_link_retargeted_by_hand_is_no_longer_ours(self):
        self.sync()
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        os.remove(self.link("leaf"))
        os.symlink(elsewhere, self.link("leaf"))
        shutil.rmtree(self.folder("_domains/plain/leaf"))
        self.sync()
        self.assertEqual(os.readlink(self.link("leaf")), elsewhere)

    def test_a_dangling_link_of_ours_is_removed(self):
        self.sync()
        self.assertTrue(os.path.islink(self.link("alpha")))
        shutil.rmtree(self.folder("_common/alpha"))
        self.sync()
        self.assertFalse(os.path.lexists(self.link("alpha")))

    def test_errors_are_reported_not_raised(self):
        os.chmod(self.skills_dir, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, self.skills_dir, stat.S_IRWXU)
        report = self.sync()
        self.assertTrue(report["errors"])


class Aliases(EngineCase):
    """Links take the name a workspace already uses for the same skill folder."""

    def reflect(self, project, name, relative):
        reflections = os.path.join(project, ".claude", "skills")
        os.makedirs(reflections, exist_ok=True)
        os.symlink(self.folder(relative), os.path.join(reflections, name))

    def test_a_workspace_reflection_renames_the_link(self):
        project = os.path.join(self.root, "workspace")
        self.reflect(project, "dom--child", "_domains/dom/child")
        self.sync()
        global_links.learn_aliases(project, self.repo, self.state)
        self.sync()
        self.assertIn("dom--child", self.linked())
        self.assertNotIn("child", self.linked())

    def test_aliases_survive_sessions_outside_the_workspace(self):
        project = os.path.join(self.root, "workspace")
        self.reflect(project, "dom--child", "_domains/dom/child")
        global_links.learn_aliases(project, self.repo, self.state)
        global_links.learn_aliases(os.path.join(self.root, "elsewhere"), self.repo, self.state)
        self.sync()
        self.assertIn("dom--child", self.linked())

    def test_only_reflections_of_this_repo_teach_names(self):
        project = os.path.join(self.root, "workspace")
        other = os.path.join(self.root, "other-repo", "skill")
        os.makedirs(other)
        reflections = os.path.join(project, ".claude", "skills")
        os.makedirs(reflections)
        os.symlink(other, os.path.join(reflections, "dom--alpha"))
        global_links.learn_aliases(project, self.repo, self.state)
        self.sync()
        self.assertIn("alpha", self.linked())
        self.assertNotIn("dom--alpha", self.linked())


def _run_sync(arguments):
    repo, skills_dir, state = arguments
    return global_links.sync(repo, skills_dir, state, exclude=("excluded",))["errors"]


class Concurrency(EngineCase):
    def test_eight_sessions_at_once_leave_the_right_links(self):
        with multiprocessing.Pool(8) as pool:
            errors = pool.map(_run_sync, [(self.repo, self.skills_dir, self.state)] * 8)
        self.assertEqual(errors, [[]] * 8)
        self.assertEqual(sorted(self.linked()), ["alpha", "child", "dom", "leaf"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
