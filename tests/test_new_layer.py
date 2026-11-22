"""`mai new-layer` and the trace check that guards everything it copies.

Why this file exists: a new skills repo is often built for someone else, from material
that lives in the builder's own repos. Nothing that identifies the builder or their
private repo may reach it: not their name or email, not their home folder, not the name
of their repo, not the names of skills they did not choose to give. When something
would leak, the result is removed and the message says exactly where the trace is.
"""
import json
import os
import subprocess
import sys

import pytest

from _lib.layer_kit import generator, leaks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "bin", "new_layer.py")


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def builder(tmp_path, monkeypatch):
    """A builder's machine: their git identity, their home and their private skills repo."""
    home = tmp_path / "home" / "builder"
    home.mkdir(parents=True)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Grace Hopper\n\temail = grace@private.example\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("HOME", str(home))
    source = tmp_path / "graces-private-skills"
    (source / "claude" / ".claude-plugin").mkdir(parents=True)
    (source / "claude" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "grace-kit", "author": {"name": "G. Hopper"}}))
    for skill in ("compiler-tips", "secret-sauce"):
        folder = source / "skills" / "_common" / skill
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: %s\ndescription: d\n---\nbody\n" % skill)
    git("init", "-q", "-b", "main", cwd=source)
    git("remote", "add", "origin", "git@github.com:ghopper/graces-private-skills.git", cwd=source)
    git("add", "-A", cwd=source)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "init", cwd=source)
    return {"home": str(home), "source": str(source)}


class TestDenylist:
    def test_holds_the_builders_identity_home_and_private_repo(self, builder):
        words = leaks.denylist([builder["source"]], keep=["Ada"])
        for expected in ("Grace Hopper", "grace@private.example", builder["home"],
                         "graces-private-skills", "ghopper", "grace-kit", "G. Hopper"):
            assert expected in words

    def test_the_new_owner_and_explicitly_allowed_words_are_kept_out(self, builder):
        words = leaks.denylist([builder["source"]], keep=["Grace Hopper", "ghopper"])
        assert "Grace Hopper" not in words and "ghopper" not in words

    def test_skills_left_behind_are_named_only_as_paths_or_code(self, builder, tmp_path):
        root = tmp_path / "out"
        (root / "skills").mkdir(parents=True)
        (root / "skills" / "a.md").write_text(
            "see `secret-sauce`\nor skills/_common/secret-sauce/SKILL.md\nthe secret sauce of cooking\n")
        left_behind = leaks.left_behind_skills(builder["source"], selected=["compiler-tips"])
        assert left_behind == ["secret-sauce"]
        findings = leaks.scan(str(root), words=[], skill_names=left_behind)
        assert [(f.line, f.word) for f in findings] == [(1, "secret-sauce"), (2, "secret-sauce")]


class TestScan:
    @pytest.mark.parametrize("text, word", [
        ('"""Written by Grace Hopper."""\n', "Grace Hopper"),
        ("contact: grace@private.example\n", "grace@private.example"),
        ("cache in {home}/.cache\n", "{home}"),
        ("fork of ghopper/graces-private-skills\n", "graces-private-skills"),
    ])
    def test_each_trace_is_found_with_its_file_and_line(self, builder, tmp_path, text, word):
        word = word.format(home=builder["home"])
        root = tmp_path / "out"
        root.mkdir()
        (root / "notes.py").write_text("ok\n" + text.format(home=builder["home"]))
        findings = leaks.scan(str(root), words=leaks.denylist([builder["source"]], keep=[]))
        assert ("notes.py", 2) in [(f.path, f.line) for f in findings]
        assert word in [f.word for f in findings]

    def test_names_match_whole_words_only(self, tmp_path):
        root = tmp_path / "out"
        root.mkdir()
        (root / "a.md").write_text("Gracefully done by AmazingGrace\n")
        assert leaks.scan(str(root), words=["Grace"]) == []

    def test_a_clean_tree_has_no_findings(self, builder, tmp_path):
        destination = tmp_path / "acme"
        generator.create(str(destination), name="acme-skills", owner="Ada")
        assert leaks.scan(str(destination), words=leaks.denylist([builder["source"]], keep=["Ada"])) == []


class TestCommandLine:
    def run(self, *args, cwd, env=None):
        environment = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, env=environment,
                              capture_output=True, text=True)

    def test_creates_the_repo_relative_to_the_callers_directory(self, tmp_path):
        caller = tmp_path / "caller"
        caller.mkdir()
        completed = self.run("acme-skills", "--owner", "Ada", cwd=str(tmp_path),
                             env={"MAICELIUM_CALLER_CWD": str(caller)})
        assert completed.returncode == 0, completed.stderr
        manifest = json.loads((caller / "acme-skills" / "claude/.claude-plugin/plugin.json").read_text())
        assert manifest["name"] == "acme-skills"
        assert "doctor.py --fix" in completed.stdout

    def test_with_takes_skill_folders_relative_to_the_caller(self, builder, tmp_path):
        completed = self.run("acme-skills", "--owner", "Ada",
                             "--with", "graces-private-skills/skills/_common/compiler-tips",
                             cwd=str(tmp_path / "home"), env={"MAICELIUM_CALLER_CWD": str(tmp_path)})
        assert completed.returncode == 0, completed.stderr
        assert (tmp_path / "acme-skills/skills/_common/compiler-tips/SKILL.md").is_file()
        assert "Skills: _common/compiler-tips" in completed.stdout

    def test_a_refusal_exits_2_with_the_reason(self, tmp_path):
        (tmp_path / "taken").mkdir()
        (tmp_path / "taken" / "x").write_text("x")
        completed = self.run("taken", "--owner", "Ada", cwd=str(tmp_path),
                             env={"MAICELIUM_CALLER_CWD": str(tmp_path)})
        assert completed.returncode == 2
        assert "not empty" in completed.stderr
