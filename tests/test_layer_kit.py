"""Layer kit: the engine and skeleton that `mai kit` copies into a new skills repo.

Why this file exists: the kit is copied into repos owned by other people. It must hold
nothing that belongs to whoever wrote it, and a freshly generated repo must pass its own
test suites before anyone relies on it.
"""
import json
import os
import re
import subprocess
import sys

import pytest

from _lib.layer_kit import generator, leaks

KIT = os.path.dirname(generator.__file__)
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="the engine uses fcntl and symlinks")

# Shapes that tie a file to one machine or person, whoever runs the tests. The reserved
# example domains (RFC 2606) are fine for test fixtures.
MACHINE_SPECIFIC = re.compile(r"/home/[^/\s]+|/Users/[^/\s]+|[A-Za-z]:\\Users\\|[\w.+-]+@(?!example\.)[\w-]+\.[\w.]+")


def copied_files():
    """What the kit copies into other people's repos: the engine and the skeleton."""
    for part in ("engine", "skeleton"):
        for folder, subfolders, names in os.walk(os.path.join(KIT, part)):
            subfolders[:] = [name for name in subfolders if name != "__pycache__"]
            for name in names:
                if not name.endswith(".pyc"):
                    yield os.path.join(folder, name)


def test_the_kit_holds_no_home_path_or_email():
    found = []
    for path in copied_files():
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if MACHINE_SPECIFIC.search(line):
                    found.append("%s:%d: %s" % (os.path.relpath(path, KIT), number, line.strip()))
    assert found == []


def test_the_kit_carries_no_trace_of_whoever_runs_the_tests():
    """The words come from this machine (git identity, home, remote owner), never from a list."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    words = leaks.denylist([repo], keep=["mAIcelium", "maicelium", os.path.basename(repo)])
    findings = []
    for part in ("engine", "skeleton"):
        findings += leaks.scan(os.path.join(KIT, part), words)
    assert leaks.describe(findings) == ""


def test_a_new_repo_has_the_layer_layout_and_its_owner_identity(tmp_path):
    destination = tmp_path / "acme-skills"
    generator.create(str(destination), name="acme-skills", owner="Ada Lovelace")
    for folder in ("skills/_common", "skills/_domains", "rules/_domains"):
        assert (destination / folder).is_dir()
    manifest = json.loads((destination / "claude/.claude-plugin/plugin.json").read_text())
    assert (manifest["name"], manifest["author"]["name"]) == ("acme-skills", "Ada Lovelace")
    registry = json.loads((destination / "claude/hooks/registry.json").read_text())
    assert list(registry) == ["session-start"]
    assert (destination / ".git").is_dir()


def test_a_new_repo_has_no_commit(tmp_path):
    destination = tmp_path / "acme-skills"
    generator.create(str(destination), name="acme-skills", owner="Ada")
    completed = subprocess.run(["git", "-C", str(destination), "rev-parse", "--verify", "-q", "HEAD"],
                               capture_output=True)
    assert completed.returncode != 0


def test_an_existing_destination_is_never_overwritten(tmp_path):
    destination = tmp_path / "taken"
    destination.mkdir()
    (destination / "mine.txt").write_text("keep")
    with pytest.raises(generator.LayerError):
        generator.create(str(destination), name="acme-skills", owner="Ada")
    assert sorted(os.listdir(destination)) == ["mine.txt"]


def test_a_plugin_name_must_be_a_folder_safe_slug(tmp_path):
    with pytest.raises(generator.LayerError):
        generator.create(str(tmp_path / "x"), name="Acme Skills!", owner="Ada")


@POSIX_ONLY
@pytest.mark.parametrize("suite", [
    "test_global_links.py", "test_dispatcher.py", "test_session_start.py",
    "test_maintenance.py", "test_doctor.py", "test_repo_invariants.py", "test_identity.py",
])
def test_a_new_repo_passes_its_own_engine_suites(tmp_path, suite):
    destination = tmp_path / "acme-skills"
    generator.create(str(destination), name="acme-skills", owner="Ada")
    completed = subprocess.run(
        [sys.executable, str(destination / "claude" / "tests" / suite)],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                 GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid"),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
