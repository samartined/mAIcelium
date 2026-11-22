"""`mai kit update <repo>`: bring a skills repo's engine up to the kit's.

Why this file exists: every skills repo carries its own copy of the engine, and its owner
must be able to take the kit's improvements without losing anything of theirs. The
upgrade replaces the engine files and the engine's hook wiring only. It never touches
skills, rules, the repo's own hooks or its identity, it stops when an engine file was
edited in the repo, and it refuses to leave a wired hook that nothing declares, because
the dispatcher would silently stop running it.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from _lib.layer_kit import generator

# The engine needs fcntl and symlinks, so the tests that run it exist only on Linux and
# macOS. They are left undefined elsewhere rather than skipped: CI allows no skipped test.
ENGINE_RUNS_HERE = os.name == "posix"


@pytest.fixture
def repo(tmp_path):
    destination = str(tmp_path / "acme-skills")
    generator.create(destination, name="acme-skills", owner="Ada")
    os.makedirs(os.path.join(destination, "skills/_common/mine"))
    with open(os.path.join(destination, "skills/_common/mine/SKILL.md"), "w") as handle:
        handle.write("---\nname: mine\ndescription: d\n---\nbody\n")
    hooks_dir = os.path.join(destination, "claude/hooks")
    for name in ("guard.py", "test_guard.py"):
        with open(os.path.join(hooks_dir, name), "w") as handle:
            handle.write("pass\n")
    registry = json.load(open(os.path.join(hooks_dir, "registry.json")))
    registry["guard"] = {"script": "guard.py", "test": "test_guard.py", "skills": ["_common/mine"],
                         "needs": [], "origin": "repo"}
    json.dump(registry, open(os.path.join(hooks_dir, "registry.json"), "w"))
    wiring = json.load(open(os.path.join(hooks_dir, "hooks.json")))
    wiring["hooks"]["PreToolUse"] = [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py" guard', "timeout": 10}]}]
    json.dump(wiring, open(os.path.join(hooks_dir, "hooks.json"), "w"))
    return destination


@pytest.fixture
def newer_kit(tmp_path, monkeypatch):
    """A later kit: one engine file changed, one added, one removed."""
    engine = str(tmp_path / "kit-engine")
    shutil.copytree(generator.ENGINE, engine, ignore=shutil.ignore_patterns("__pycache__"))
    with open(os.path.join(engine, "maintenance.py"), "a") as handle:
        handle.write("\n# newer\n")
    with open(os.path.join(engine, "added.py"), "w") as handle:
        handle.write("# new engine file\n")
    os.remove(os.path.join(engine, "tests", "test_identity.py"))
    monkeypatch.setattr(generator, "ENGINE", engine)
    return engine


def read(repo, relative):
    with open(os.path.join(repo, relative), encoding="utf-8") as handle:
        return handle.read()


def test_replaces_adds_and_removes_engine_files(repo, newer_kit):
    report = generator.upgrade(repo)
    assert read(repo, "claude/maintenance.py").endswith("# newer\n")
    assert os.path.isfile(os.path.join(repo, "claude/added.py"))
    assert not os.path.exists(os.path.join(repo, "claude/tests/test_identity.py"))
    assert (report["updated"], report["added"], report["removed"]) == (
        ["maintenance.py"], ["added.py"], ["tests/test_identity.py"])
    recorded = json.loads(read(repo, "claude/engine.json"))["files"]
    assert "added.py" in recorded and "tests/test_identity.py" not in recorded


def test_leaves_the_owners_files_alone(repo, newer_kit):
    before = {relative: read(repo, relative) for relative in (
        "skills/_common/mine/SKILL.md", "claude/.claude-plugin/plugin.json", "claude/global.json",
        "claude/hard-rules.md", "README.md", "AGENTS.md", "claude/hooks/guard.py")}
    generator.upgrade(repo)
    assert {relative: read(repo, relative) for relative in before} == before
    registry = json.loads(read(repo, "claude/hooks/registry.json"))
    assert registry["guard"]["origin"] == "repo"
    assert "guard" in read(repo, "claude/hooks/hooks.json")


def test_an_engine_file_edited_in_the_repo_stops_the_upgrade(repo, newer_kit):
    with open(os.path.join(repo, "claude/doctor.py"), "a") as handle:
        handle.write("# local tweak\n")
    with pytest.raises(generator.LayerError) as refusal:
        generator.upgrade(repo)
    assert "doctor.py" in str(refusal.value)
    assert not read(repo, "claude/maintenance.py").endswith("# newer\n")
    generator.upgrade(repo, force=True)
    assert "# local tweak" not in read(repo, "claude/doctor.py")


def test_a_repo_without_an_engine_record_needs_force(repo, newer_kit):
    os.remove(os.path.join(repo, "claude/engine.json"))
    with pytest.raises(generator.LayerError):
        generator.upgrade(repo)
    generator.upgrade(repo, force=True)
    assert os.path.isfile(os.path.join(repo, "claude/engine.json"))


def test_a_wired_hook_that_nothing_declares_stops_the_upgrade(repo, newer_kit):
    registry = json.loads(read(repo, "claude/hooks/registry.json"))
    del registry["guard"]
    json.dump(registry, open(os.path.join(repo, "claude/hooks/registry.json"), "w"))
    with pytest.raises(generator.LayerError) as refusal:
        generator.upgrade(repo, force=True)
    assert "guard" in str(refusal.value)


def test_an_up_to_date_repo_changes_nothing(repo):
    assert generator.upgrade(repo) == {"updated": [], "added": [], "removed": []}


if ENGINE_RUNS_HERE:
    def test_the_upgraded_repo_keeps_its_invariants(repo, newer_kit):
        generator.upgrade(repo)
        completed = subprocess.run([sys.executable, os.path.join(repo, "claude/tests/test_repo_invariants.py")],
                                   capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_the_command_line_upgrades_and_reports(repo, tmp_path):
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "kit.py")
    os.remove(os.path.join(repo, "claude/engine.json"))
    refused = subprocess.run([sys.executable, script, "update", "./acme-skills"], capture_output=True, text=True,
                             env=dict(os.environ, MAICELIUM_CALLER_CWD=str(tmp_path), MAICELIUM_ROOT=str(tmp_path / "ws")))
    assert refused.returncode == 2 and "--force" in refused.stderr
    done = subprocess.run([sys.executable, script, "update", "./acme-skills", "--force"], capture_output=True,
                          text=True, env=dict(os.environ, MAICELIUM_CALLER_CWD=str(tmp_path), MAICELIUM_ROOT=str(tmp_path / "ws")))
    assert done.returncode == 0, done.stderr
    assert "engine is up to date" in done.stdout
