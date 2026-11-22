"""`mai kit import`: turn a repo of skills and rules, in any agent's format, into a skills repo.

Why this file exists: people keep their skills and rules in the format of whichever agent
they use. Conversion runs in two steps. `plan` writes an editable map of what each file
is and where it goes; `apply` builds the new repo from that map, never from guesses the
person did not see. The source is never changed, and the result passes the same trace
check as any other copy.

Formats covered: skill folders (SKILL.md), Cursor rules (.mdc), Claude Code commands,
Windsurf rules (trigger + globs), Cline rules, Copilot instructions (applyTo), and the
single instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules) split by section.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

from _lib.layer_kit import generator, importer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "bin", "kit.py")
# The engine needs fcntl and symlinks, so the tests that run it exist only on Linux and
# macOS. They are left undefined elsewhere rather than skipped: CI allows no skipped test.
ENGINE_RUNS_HERE = os.name == "posix"


def write(root, relative, text):
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def tree_digest(root):
    digest = hashlib.sha256()
    for folder, subfolders, names in os.walk(root):
        subfolders.sort()
        for name in sorted(names):
            path = os.path.join(folder, name)
            digest.update(os.path.relpath(path, root).encode())
            with open(path, "rb") as handle:
                digest.update(handle.read())
    return digest.hexdigest()


@pytest.fixture
def source(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Grace Hopper\n\temail = grace@private.example\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = str(tmp_path / "old-agent-config")
    write(root, ".claude/skills/deploy-check/SKILL.md",
          "---\nname: deploy-check\ndescription: Check a terraform deploy\n---\nSteps.\n")
    write(root, ".claude/skills/deploy-check/check.sh", "echo ok\n")
    write(root, "skills/_domains/data/sql-style/SKILL.md", "---\nname: sql-style\ndescription: SQL style\n---\nUse CTEs.\n")
    write(root, ".cursor/rules/react-components.mdc",
          "---\ndescription: React components\nglobs: src/**/*.tsx\nalwaysApply: false\n---\nUse hooks.\n")
    write(root, ".claude/commands/release-notes.md",
          "---\ndescription: Draft release notes from the git log\nallowed-tools: Bash(git log:*)\n---\n"
          "Read the log and draft notes for $ARGUMENTS.\n")
    write(root, ".windsurf/rules/python-style.md",
          "---\ntrigger: glob\nglobs: \"**/*.py\"\ndescription: Python style\n---\nUse type hints.\n")
    write(root, ".windsurf/rules/always.md", "---\ntrigger: always_on\n---\nBe brief.\n")
    write(root, ".clinerules/commits.md", "Write commits in the imperative mood.\n")
    write(root, ".github/copilot-instructions.md", "Prefer small pull requests.\n")
    write(root, ".github/instructions/docker.instructions.md",
          "---\napplyTo: \"**/Dockerfile\"\n---\nPin base images.\n")
    write(root, "CLAUDE.md",
          "# Team notes\n\n## Project overview\nThis repo holds the billing service.\n\n"
          "## Code review\nEvery change needs one approval.\n\n## Security\nNever log secrets.\n")
    write(root, "notes/todo.txt", "buy milk\n")
    return root


def plan(source):
    return importer.plan(source)


def item(mapping, origin):
    return next(entry for entry in mapping["items"] if entry["from"] == origin)


class TestPlan:
    def test_every_format_is_recognised(self, source):
        mapping = plan(source)
        kinds = {entry["from"]: entry["kind"] for entry in mapping["items"]}
        assert kinds == {
            ".claude/skills/deploy-check": "skill",
            "skills/_domains/data/sql-style": "skill",
            ".cursor/rules/react-components.mdc": "cursor-rule",
            ".claude/commands/release-notes.md": "claude-command",
            ".windsurf/rules/python-style.md": "windsurf-rule",
            ".windsurf/rules/always.md": "windsurf-rule",
            ".clinerules/commits.md": "cline-rule",
            ".github/copilot-instructions.md": "copilot-instructions",
            ".github/instructions/docker.instructions.md": "copilot-instructions",
            "CLAUDE.md": "instructions-file",
            "notes/todo.txt": "unknown",
        }

    def test_targets_follow_the_layer_layout_and_guess_the_domain(self, source):
        mapping = plan(source)
        assert item(mapping, ".claude/skills/deploy-check")["to"] == "skills/_domains/devops/deploy-check"
        assert item(mapping, "skills/_domains/data/sql-style")["to"] == "skills/_domains/data/sql-style"
        assert item(mapping, ".cursor/rules/react-components.mdc")["to"] == "rules/_domains/frontend/react-components.mdc"
        assert item(mapping, ".claude/commands/release-notes.md")["to"] == "skills/_common/release-notes"
        assert item(mapping, ".clinerules/commits.md")["to"] == "rules/_domains/general/commits.mdc"
        assert item(mapping, "notes/todo.txt")["action"] == "skip"

    def test_an_instructions_file_is_split_and_project_context_is_left_out(self, source):
        sections = item(plan(source), "CLAUDE.md")["sections"]
        assert [(s["heading"], s["action"]) for s in sections] == [
            ("Project overview", "skip"), ("Code review", "convert"), ("Security", "convert")]
        assert sections[1]["to"] == "rules/_domains/general/code-review.mdc"

    def test_planning_changes_nothing_in_the_source(self, source):
        before = tree_digest(source)
        plan(source)
        assert tree_digest(source) == before


class TestApply:
    def build(self, tmp_path, mapping, allow=()):
        destination = str(tmp_path / "acme-skills")
        importer.apply(mapping, destination, name="acme-skills", owner="Ada", allow=allow)
        return destination

    def read(self, destination, relative):
        with open(os.path.join(destination, relative), encoding="utf-8") as handle:
            return handle.read()

    def test_skills_are_copied_whole(self, tmp_path, source):
        destination = self.build(tmp_path, plan(source))
        assert sorted(os.listdir(os.path.join(destination, "skills/_domains/devops/deploy-check"))) == [
            "SKILL.md", "check.sh"]

    def test_a_skill_name_that_is_not_a_folder_name_is_made_one(self, tmp_path, source):
        write(source, ".agents/skills/odd/SKILL.md", "---\nname: Odd Helper\ndescription: d\n---\nbody\n")
        mapping = plan(source)
        assert item(mapping, ".agents/skills/odd")["to"] == "skills/_common/odd-helper"
        destination = self.build(tmp_path, mapping)
        assert "\nname: odd-helper\n" in self.read(destination, "skills/_common/odd-helper/SKILL.md")

    def test_a_command_becomes_a_skill_named_after_its_folder(self, tmp_path, source):
        destination = self.build(tmp_path, plan(source))
        text = self.read(destination, "skills/_common/release-notes/SKILL.md")
        assert text.startswith("---\nname: release-notes\ndescription: Draft release notes from the git log\n---\n")
        assert "$ARGUMENTS" in text and "allowed-tools" not in text

    @pytest.mark.parametrize("target, expected", [
        ("rules/_domains/general/python-style.mdc", "description: Python style\nglobs: **/*.py\nalwaysApply: false"),
        ("rules/_domains/general/always.mdc", "alwaysApply: true"),
        ("rules/_domains/general/commits.mdc", "alwaysApply: true"),
        ("rules/_domains/general/copilot-instructions.mdc", "alwaysApply: true"),
        ("rules/_domains/devops/docker.mdc", "globs: **/Dockerfile\nalwaysApply: false"),
        ("rules/_domains/frontend/react-components.mdc", "globs: src/**/*.tsx\nalwaysApply: false"),
    ])
    def test_rules_become_mdc_with_their_scope(self, tmp_path, source, target, expected):
        destination = self.build(tmp_path, plan(source))
        assert expected in self.read(destination, target)

    def test_instruction_sections_become_always_on_rules(self, tmp_path, source):
        destination = self.build(tmp_path, plan(source))
        text = self.read(destination, "rules/_domains/general/security.mdc")
        assert text == "---\ndescription: Security\nalwaysApply: true\n---\nNever log secrets.\n"
        assert not os.path.exists(os.path.join(destination, "rules/_domains/general/project-overview.mdc"))

    def test_the_edited_map_is_what_counts(self, tmp_path, source):
        mapping = plan(source)
        item(mapping, ".cursor/rules/react-components.mdc")["to"] = "rules/_domains/web/react.mdc"
        item(mapping, ".windsurf/rules/always.md")["action"] = "skip"
        destination = self.build(tmp_path, mapping)
        assert os.path.isfile(os.path.join(destination, "rules/_domains/web/react.mdc"))
        assert not os.path.exists(os.path.join(destination, "rules/_domains/general/always.mdc"))

    def test_the_source_is_never_changed(self, tmp_path, source):
        before = tree_digest(source)
        self.build(tmp_path, plan(source))
        assert tree_digest(source) == before

    def test_two_items_aimed_at_one_place_are_refused(self, tmp_path, source):
        mapping = plan(source)
        item(mapping, ".windsurf/rules/always.md")["to"] = item(mapping, ".clinerules/commits.md")["to"]
        with pytest.raises(generator.LayerError) as refusal:
            self.build(tmp_path, mapping)
        assert "commits.mdc" in str(refusal.value)
        assert not os.path.exists(tmp_path / "acme-skills")

    def test_traces_of_the_source_owner_are_refused_unless_allowed(self, tmp_path, source):
        write(source, ".clinerules/commits.md", "Ask grace@private.example before merging.\n")
        with pytest.raises(generator.LayerError):
            self.build(tmp_path, plan(source))
        assert not os.path.exists(tmp_path / "acme-skills")
        self.build(tmp_path, plan(source), allow=["grace@private.example"])

    if ENGINE_RUNS_HERE:
        def test_the_result_keeps_the_repo_invariants(self, tmp_path, source):
            destination = self.build(tmp_path, plan(source))
            completed = subprocess.run([sys.executable, os.path.join(destination, "claude/tests/test_repo_invariants.py")],
                                       capture_output=True, text=True)
            assert completed.returncode == 0, completed.stdout + completed.stderr

class TestCommandLine:
    def test_plan_then_apply(self, tmp_path, source):
        env = dict(os.environ, MAICELIUM_CALLER_CWD=str(tmp_path))
        planned = subprocess.run([sys.executable, SCRIPT, "import", "plan", source, "--out", "map.json"],
                                 capture_output=True, text=True, env=env)
        assert planned.returncode == 0, planned.stderr
        assert json.loads((tmp_path / "map.json").read_text())["source"] == source
        applied = subprocess.run([sys.executable, SCRIPT, "import", "apply", "map.json", "acme-skills", "--owner", "Ada"],
                                 capture_output=True, text=True, env=env)
        assert applied.returncode == 0, applied.stderr
        assert (tmp_path / "acme-skills/rules/_domains/general/security.mdc").is_file()
