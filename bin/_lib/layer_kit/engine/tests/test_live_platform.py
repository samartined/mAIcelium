#!/usr/bin/env python3
"""Live characterization of the Claude Code behaviour the global consumption relies on.

Run: python3 claude/tests/test_live_platform.py

Why this file exists: skills and hooks reach every session through personal symlinks
and a hooks-only plugin, and that design is only correct while Claude Code keeps a few
behaviours: a personal and a project skill with the same `name:` load once, a plugin
linked under ~/.claude/skills/ loads in place and runs its hooks, and a broken personal
link hides nothing. Those behaviours are not ours, so they are pinned here against the
real CLI. Each run starts two short headless sessions on the cheapest model, saves no
session to disk, and removes every probe it created, whatever happens.

The probes live under ~/.claude/skills/ for a few seconds, with names that start with
`probe-<random>`. Other sessions running at that moment may see them briefly.
"""

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import textwrap
import unittest

PERSONAL_SKILLS = os.path.expanduser("~/.claude/skills")
SESSION_TIMEOUT_SECONDS = 240
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def write_skill(folder, name, description):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: %s\ndescription: %s\n---\nProbe body.\n" % (name, description))


def run_headless_session(cwd):
    """Start one headless session in cwd; return (init message, every output line)."""
    command = [
        "claude", "-p", "--no-session-persistence", "--model", "haiku", "--max-turns", "1",
        "--output-format", "stream-json", "--verbose", "Reply with the single word ok.",
    ]
    environment = dict(os.environ, SKILLS_REPO_NESTED="1")
    completed = subprocess.run(
        command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=SESSION_TIMEOUT_SECONDS,
    )
    lines = completed.stdout.splitlines()
    for line in lines:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("type") == "system" and message.get("subtype") == "init":
            return message, lines
    raise AssertionError("no init message; stderr:\n" + completed.stderr[-2000:])


class ProbeWorkspace:
    """Temporary probe tree plus the personal links it adds; removes both on close."""

    def __init__(self):
        self.prefix = "probe-" + secrets.token_hex(3)
        self.root = tempfile.mkdtemp(prefix=self.prefix + "-")
        self.project = os.path.join(self.root, "project")
        os.makedirs(os.path.join(self.project, ".claude", "skills"))
        self.personal_links = []

    def name(self, suffix):
        return "%s-%s" % (self.prefix, suffix)

    def source(self, suffix):
        return os.path.join(self.root, "sources", suffix)

    def link_personal(self, link_name, target):
        path = os.path.join(PERSONAL_SKILLS, link_name)
        os.symlink(target, path)
        self.personal_links.append(path)
        return path

    def link_project(self, link_name, target):
        os.symlink(target, os.path.join(self.project, ".claude", "skills", link_name))

    def close(self):
        for path in self.personal_links:
            if os.path.islink(path):
                os.remove(path)
        shutil.rmtree(self.root, ignore_errors=True)


def entries_containing(skills, fragment):
    return [skill for skill in skills if fragment in skill]


class SkillFusion(unittest.TestCase):
    """One session covering L1, L2, L3, L8 and a control."""

    @classmethod
    def setUpClass(cls):
        probe = cls.probe = ProbeWorkspace()
        try:
            # Control: two different skills must both be listed, so counting can see two.
            write_skill(probe.source("control-a"), probe.name("control-a"), "probe control a")
            write_skill(probe.source("control-b"), probe.name("control-b"), "probe control b")
            probe.link_personal(probe.name("control-a"), probe.source("control-a"))
            probe.link_project(probe.name("control-b"), probe.source("control-b"))

            # L1: the real case. Same skill folder, personal and project links named differently.
            write_skill(probe.source("l1"), probe.name("l1"), "probe l1")
            probe.link_personal(probe.name("l1"), probe.source("l1"))
            probe.link_project("zz--" + probe.name("l1"), probe.source("l1"))

            # L2: same name:, different folder names and different targets.
            write_skill(probe.source("l2-personal"), probe.name("l2"), "probe l2 personal copy")
            write_skill(probe.source("l2-project"), probe.name("l2"), "probe l2 project copy")
            probe.link_personal(probe.name("l2-p"), probe.source("l2-personal"))
            probe.link_project("zz--" + probe.name("l2-q"), probe.source("l2-project"))

            # L3: same folder name, different name: (recorded, not required).
            write_skill(probe.source("l3-alpha"), probe.name("l3-alpha"), "probe l3 alpha")
            write_skill(probe.source("l3-beta"), probe.name("l3-beta"), "probe l3 beta")
            probe.link_personal(probe.name("l3"), probe.source("l3-alpha"))
            probe.link_project(probe.name("l3"), probe.source("l3-beta"))

            # L8: broken personal links must not hide valid project skills.
            write_skill(probe.source("l8-renamed"), probe.name("l8-renamed"), "probe l8 renamed")
            write_skill(probe.source("l8-same"), probe.name("l8-same"), "probe l8 same")
            missing = os.path.join(probe.root, "moved-away")
            probe.link_personal(probe.name("l8-renamed"), missing)
            probe.link_project("zz--" + probe.name("l8-renamed"), probe.source("l8-renamed"))
            probe.link_personal(probe.name("l8-same"), missing)
            probe.link_project(probe.name("l8-same"), probe.source("l8-same"))

            init, _ = run_headless_session(probe.project)
            cls.skills = init.get("skills") or []
        except BaseException:
            probe.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.probe.close()

    def test_control_two_different_skills_are_both_listed(self):
        self.assertEqual(len(entries_containing(self.skills, self.probe.name("control-"))), 2)

    def test_l1_same_skill_linked_twice_loads_once_under_the_personal_name(self):
        self.assertEqual(entries_containing(self.skills, self.probe.name("l1")), [self.probe.name("l1")])

    def test_l2_the_name_field_alone_does_not_merge_skills(self):
        # Fusion keys are the folder name and the resolved target, never `name:` alone.
        self.assertEqual(len(entries_containing(self.skills, self.probe.name("l2"))), 2)

    def test_l3_a_shared_folder_name_merges_even_different_skills(self):
        # A personal skill hides any project skill whose folder has the same name.
        self.assertEqual(entries_containing(self.skills, self.probe.name("l3")), [self.probe.name("l3")])

    def test_l8_broken_personal_link_hides_no_project_skill(self):
        self.assertEqual(len(entries_containing(self.skills, self.probe.name("l8-renamed"))), 1)
        self.assertEqual(len(entries_containing(self.skills, self.probe.name("l8-same"))), 1)


class LinkedPlugin(unittest.TestCase):
    """One session covering L4, L5, L6 and L7 with a hooks-only plugin linked in place."""

    @classmethod
    def setUpClass(cls):
        probe = cls.probe = ProbeWorkspace()
        try:
            plugin = os.path.join(probe.root, "plugin")
            os.makedirs(os.path.join(plugin, ".claude-plugin"))
            os.makedirs(os.path.join(plugin, "hooks"))
            cls.plugin_name = probe.name("plugin")
            with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w") as handle:
                json.dump({"name": cls.plugin_name, "version": "0.0.1"}, handle)

            cls.marker = os.path.join(probe.root, "hook-runs.jsonl")
            cls.late_skill = probe.name("l6")
            write_skill(probe.source("l6"), cls.late_skill, "probe l6")
            late_link = os.path.join(PERSONAL_SKILLS, cls.late_skill)
            probe.personal_links.append(late_link)
            cls.system_text = probe.name("l7").upper()
            mark = os.path.join(plugin, "hooks", "mark.py")
            with open(mark, "w") as handle:
                handle.write(textwrap.dedent("""\
                    #!/usr/bin/env python3
                    import json, os, sys
                    event = sys.argv[1]
                    with open(%r, "a") as out:
                        out.write(json.dumps({"event": event,
                                              "plugin_root": os.environ.get("CLAUDE_PLUGIN_ROOT")}) + "\\n")
                    if event == "SessionStart":
                        if not os.path.lexists(%r):
                            os.symlink(%r, %r)
                        print(json.dumps({"systemMessage": %r}))
                    """) % (cls.marker, late_link, probe.source("l6"), late_link, cls.system_text))
            os.chmod(mark, 0o755)
            command = "${CLAUDE_PLUGIN_ROOT}/hooks/mark.py"
            hooks = {"hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": command + " SessionStart"}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command + " UserPromptSubmit"}]}],
            }}
            with open(os.path.join(plugin, "hooks", "hooks.json"), "w") as handle:
                json.dump(hooks, handle)
            cls.plugin_link = probe.link_personal(cls.plugin_name, plugin)

            init, cls.lines = run_headless_session(probe.project)
            cls.skills = init.get("skills") or []
            cls.plugins = init.get("plugins") or []
            cls.runs = []
            if os.path.exists(cls.marker):
                with open(cls.marker) as handle:
                    cls.runs = [json.loads(line) for line in handle if line.strip()]
        except BaseException:
            probe.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.probe.close()

    def test_l4_plugin_linked_under_personal_skills_loads(self):
        self.assertIn(self.plugin_name, [plugin.get("name") for plugin in self.plugins])

    def test_l4_its_hooks_run_with_the_link_as_plugin_root(self):
        events = {run["event"] for run in self.runs}
        self.assertEqual(events, {"SessionStart", "UserPromptSubmit"})
        self.assertEqual({run["plugin_root"] for run in self.runs}, {self.plugin_link})

    def test_l5_a_plugin_without_skills_adds_none(self):
        self.assertEqual([skill for skill in self.skills if skill.startswith(self.plugin_name + ":")], [])

    def test_l6_a_link_created_at_session_start_waits_for_the_next_session(self):
        # The skill list is built before SessionStart hooks finish.
        self.assertNotIn(self.late_skill, self.skills)

    def test_l7_session_start_system_message_reaches_the_output(self):
        self.assertTrue(any(self.system_text in line for line in self.lines))


def repo_skill_names():
    names = set()
    for folder, _, files in os.walk(os.path.join(REPO, "skills")):
        if "SKILL.md" in files:
            names.add(os.path.basename(folder))
    return names


def checkouts_of_this_repo():
    common = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {os.path.realpath(REPO), os.path.realpath(os.path.dirname(common))}


def is_ours(name, checkouts):
    """A listed name comes from this repo when its personal link resolves into a checkout."""
    target = os.path.realpath(os.path.join(PERSONAL_SKILLS, name))
    return any(target.startswith(checkout + os.sep) for checkout in checkouts)


class BuiltInNames(unittest.TestCase):
    """A repo skill named like a built-in skill or command would silently replace it."""

    def test_no_repo_skill_shares_a_name_with_a_built_in(self):
        project = tempfile.mkdtemp(prefix="probe-builtins-")
        try:
            init, _ = run_headless_session(project)
        finally:
            shutil.rmtree(project, ignore_errors=True)
        listed = set(init.get("skills") or []) | set(init.get("slash_commands") or [])
        checkouts = checkouts_of_this_repo()
        built_in = {name for name in listed if ":" not in name and not is_ours(name, checkouts)}
        self.assertEqual(sorted(repo_skill_names() & built_in), [])


class PluginManifest(unittest.TestCase):
    def test_the_official_validator_accepts_the_plugin(self):
        completed = subprocess.run(
            ["claude", "plugin", "validate", os.path.join(REPO, "claude")],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=SESSION_TIMEOUT_SECONDS,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout[-1500:])
        self.assertIn("Validation passed", completed.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
