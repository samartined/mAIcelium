"""bin/check_public_text.py: personal and client traces never reach the public repo.

Fixture strings that look like real traces are built by concatenation, so this file
itself passes the check it tests.
"""
import json
import os
import subprocess
import sys

import pytest

import check_public_text as check

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "bin", "check_public_text.py")
HOME = "/" + "Users/jdoe"
LINUX_HOME = "/" + "home/jdoe"
REAL_EMAIL = "jdoe" + "@" + "corp-mail.net"
NOREPLY = "123+jdoe@users.noreply.github.com"
CLIENT = "Wid" + "getco"


def lines(text, words=()):
    return check.scan_text("f.md", text, check.compile_words(words))


@pytest.mark.parametrize("text", [HOME + "/Dev/repo", "cd " + LINUX_HOME, "C:/" + "Users/jdoe/x"])
def test_personal_home_paths_are_flagged(text):
    assert [f.kind for f in lines(text)] == ["home path"]


@pytest.mark.parametrize("text", [
    "/Users/<name>/Dev", "/home/user/dev/my-api", "~/Dev/mAIcelium", "/home/runner/work",
    "$HOME/.claude", "/Users/$USER/x",
])
def test_placeholder_home_paths_pass(text):
    assert lines(text) == []


def test_real_email_is_flagged():
    assert [f.kind for f in lines("contact " + REAL_EMAIL)] == ["email"]


@pytest.mark.parametrize("text", [
    "grace@private.example", "t@example.invalid", "a@example.com", NOREPLY,
    "git@github.com:org/repo.git", "@pytest.fixture", "user@localhost.test",
])
def test_reserved_and_noreply_emails_pass(text):
    assert lines(text) == []


def test_private_words_match_whole_words_case_insensitively():
    words = [CLIENT]
    assert [f.kind for f in lines("the " + CLIENT.lower() + "-iac repo", words)] == ["private word"]
    assert lines("the " + CLIENT + "s plural is another word", words) == []


def test_words_come_from_env_and_json_file(tmp_path, monkeypatch):
    source = tmp_path / "global.json"
    source.write_text(json.dumps({"private_words": ["Alpha", "Beta"]}))
    monkeypatch.setenv("PRIVATE_WORDS", "Gamma\nDelta, Epsilon")
    assert sorted(check.load_words(str(source))) == ["Alpha", "Beta", "Delta", "Epsilon", "Gamma"]


def git(cwd, *args, env=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "J Doe")
    git(root, "config", "user.email", NOREPLY)
    (root / "a.md").write_text("hello\n")
    git(root, "add", "a.md")
    git(root, "commit", "-q", "-m", "base")
    return root


def commit(root, message, email=NOREPLY):
    (root / "a.md").write_text((root / "a.md").read_text() + "x\n")
    git(root, "commit", "-q", "-am", message,
        env=dict(os.environ, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_EMAIL=email))


def test_clean_commits_pass(repo):
    commit(repo, "docs: tidy")
    assert check.scan_commits(str(repo), "HEAD~1..HEAD", check.compile_words([])) == []


def test_ai_attribution_in_a_message_is_flagged(repo):
    commit(repo, "feat: x\n\nCo-Authored-By: " + "Claude <noreply@" + "anthropic.com>")
    kinds = [f.kind for f in check.scan_commits(str(repo), "HEAD~1..HEAD", check.compile_words([]))]
    assert "ai attribution" in kinds


def test_a_non_noreply_identity_is_flagged(repo):
    commit(repo, "fix: y", email=REAL_EMAIL)
    kinds = [f.kind for f in check.scan_commits(str(repo), "HEAD~1..HEAD", check.compile_words([]))]
    assert kinds == ["identity", "identity"]


def test_cli_reports_file_and_line_and_fails(tmp_path):
    (tmp_path / "doc.md").write_text("ok\nsee " + HOME + "/x\n")
    out = subprocess.run([sys.executable, SCRIPT, str(tmp_path / "doc.md")], capture_output=True, text=True)
    assert out.returncode == 1
    assert "doc.md:2" in out.stdout and "home path" in out.stdout


def test_the_repo_itself_has_no_generic_traces():
    """Tracked files carry no home path or real email, whoever runs the tests."""
    findings = check.scan_files(check.tracked_files(REPO), check.compile_words([]), root=REPO)
    assert check.describe(findings) == ""
