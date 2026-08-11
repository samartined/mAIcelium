"""Tests for bin/add_project.py and bin/remove_project.py.

These tests build a miniature workspace under tmp_path that mimics the
real layout (bin/, bin/_lib/, mesh/conventions.json) so the scripts can
operate against a clean root via the ``--root`` injection done by
``resolve_root`` patching.
"""
import io
import os
import shutil
import subprocess
import sys
import textwrap
from contextlib import redirect_stdout

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import add_project  # noqa: E402
import remove_project  # noqa: E402
import separate_git  # noqa: E402

from _marks import requires_symlink


def _bootstrap_workspace(tmp_path):
    """Create a minimal real workspace under tmp_path/workspace and return its path.

    The workspace contains:
      - bin/ symlink to the real bin/ so the scripts can import _lib
      - mesh/conventions.json copied from the real one
      - empty projects/ directory
    """
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "projects").mkdir()
    (ws / "mesh").mkdir()
    shutil.copy(
        os.path.join(_REPO_ROOT, "mesh", "conventions.json"),
        str(ws / "mesh" / "conventions.json"),
    )
    return ws


def _make_fake_project(base, name, with_rule=True, with_skill=True):
    """Create a fake project repo with optional rule and skill content."""
    repo = base / name
    repo.mkdir()
    if with_rule:
        rules_dir = repo / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rule.md").write_text("# test rule\n")
    if with_skill:
        skill_dir = repo / ".cursor" / "skills" / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill body\n")
    return repo


def _patch_root(monkeypatch, workspace):
    """Force resolve_root to return our temp workspace for all modules."""
    workspace_str = str(workspace)
    monkeypatch.setattr(add_project, "resolve_root", lambda: workspace_str)
    monkeypatch.setattr(remove_project, "resolve_root", lambda: workspace_str)
    monkeypatch.setattr(separate_git, "resolve_root", lambda: workspace_str)


# ────────────────────────────────────────────────────────────────────────────
# add_project
# ────────────────────────────────────────────────────────────────────────────


@requires_symlink
def test_add_project_creates_symlinks_and_workspace_entry(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "demo", str(repo)])

    assert rc == 0, buf.getvalue()

    link = ws / "projects" / "demo"
    assert link.is_symlink()
    assert os.path.realpath(str(link)) == os.path.realpath(str(repo))

    rule_link = ws / ".cursor" / "rules" / "demo--rule.md"
    assert rule_link.is_symlink()

    skill_link = ws / ".cursor" / "skills-cursor" / "demo--myskill"
    assert skill_link.is_symlink()

    wf = ws / "WORKSPACE.md"
    assert wf.is_file()
    content = wf.read_text()
    assert "- name: demo" in content
    assert f"path: {os.path.realpath(str(repo))}" in content

    code_ws = ws / "mAIcelium.code-workspace"
    assert code_ws.is_file()

    claude_ctx = ws / ".claude" / "projects-context.md"
    assert claude_ctx.is_file()


def test_add_project_rejects_invalid_name(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "bad name!", str(repo)])

    assert rc == 1
    assert "Invalid project name" in buf.getvalue()


def test_add_project_rejects_missing_path(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    bogus = tmp_path / "does_not_exist"

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "demo", str(bogus)])

    assert rc == 1
    assert "does not exist" in buf.getvalue()


@requires_symlink
def test_add_project_refuses_duplicate(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        add_project.main(["add_project.py", "demo", str(repo)])
        rc = add_project.main(["add_project.py", "demo", str(repo)])

    assert rc == 1
    assert "already exists" in buf.getvalue()


@requires_symlink
def test_add_project_code_only_skips_imports(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "--code-only", "demo", str(repo)])

    assert rc == 0
    assert (ws / "projects" / "demo").is_symlink()
    assert not (ws / ".cursor" / "rules" / "demo--rule.md").exists()
    assert not (ws / ".cursor" / "skills-cursor" / "demo--myskill").exists()


# ────────────────────────────────────────────────────────────────────────────
# remove_project
# ────────────────────────────────────────────────────────────────────────────


@requires_symlink
def test_add_then_remove_leaves_clean_state(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        add_project.main(["add_project.py", "demo", str(repo)])
        rc = remove_project.main(["remove_project.py", "demo"])

    assert rc == 0, buf.getvalue()

    assert not (ws / "projects" / "demo").exists()
    assert not (ws / "projects" / "demo").is_symlink()
    assert not (ws / ".cursor" / "rules" / "demo--rule.md").exists()
    assert not (ws / ".cursor" / "skills-cursor" / "demo--myskill").exists()

    content = (ws / "WORKSPACE.md").read_text()
    assert "- name: demo" not in content
    assert f"path: {os.path.realpath(str(repo))}" not in content

    assert repo.is_dir()
    assert (repo / ".cursor" / "rules" / "rule.md").is_file()


def test_remove_nonexistent_project_does_not_crash(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = remove_project.main(["remove_project.py", "ghost"])

    out = buf.getvalue()
    assert rc == 1
    assert "does not exist" in out


def test_remove_invalid_name(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = remove_project.main(["remove_project.py", "bad name!"])

    assert rc == 1
    assert "Invalid project name" in buf.getvalue()


def test_remove_no_arg_shows_usage(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = remove_project.main(["remove_project.py"])

    out = buf.getvalue()
    assert rc == 1
    assert "Usage:" in out
    assert "Active projects" in out


@requires_symlink
def test_remove_preserves_other_sections(tmp_path, monkeypatch):
    """WORKSPACE.md with mesh_layers + projects: remove keeps mesh_layers intact."""
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            f"""\
            # Active workspace

            mesh_layers:
              - name: client_a
                path: /abs/path/client_a
                client: clienta
              - name: client_b
                path: /abs/path/client_b

            projects:
            - name: demo
              path: {os.path.realpath(str(repo))}
              added: 2024-01-01T00:00:00
            - name: keep_me
              path: /some/where
              added: 2024-01-02T00:00:00

            mcp_source:
              path: /some/mcp
            """
        )
    )

    os.symlink(str(repo), str(ws / "projects" / "demo"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = remove_project.main(["remove_project.py", "demo"])

    assert rc == 0, buf.getvalue()

    after = wf.read_text()
    assert "mesh_layers:" in after
    assert "client_a" in after
    assert "client_b" in after
    assert "mcp_source:" in after
    assert "keep_me" in after
    assert "- name: demo" not in after
    assert os.path.realpath(str(repo)) not in after


@requires_symlink
def test_remove_cleans_agents_projects_tree(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    agents_proj = ws / ".agents" / "projects" / "demo"
    agents_proj.mkdir(parents=True)
    target = tmp_path / "agents-target"
    target.mkdir()
    os.symlink(str(target), str(agents_proj / "link"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        add_project.main(["add_project.py", "demo", str(repo)])
        rc = remove_project.main(["remove_project.py", "demo"])

    assert rc == 0
    assert not agents_proj.exists()
    assert target.is_dir()


# ────────────────────────────────────────────────────────────────────────────
# separate_git (smoke test only)
# ────────────────────────────────────────────────────────────────────────────


def test_separate_git_help_smoke():
    """separate_git imports cleanly and --help prints usage."""
    result = subprocess.run(
        [sys.executable, os.path.join(_REPO_ROOT, "bin", "separate_git.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "separate_git.py" in result.stdout
    assert ".git" in result.stdout


def test_separate_git_no_git_dir_errors_clean(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = separate_git.main(["separate_git.py"])

    out = buf.getvalue()
    assert rc == 1
    assert "No .git directory found" in out


def test_separate_git_moves_git_and_emits_alias(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    (ws / "bin").mkdir()
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = separate_git.main(["separate_git.py"])

    assert rc == 0, buf.getvalue()
    assert not (ws / ".git").exists()
    backup = tmp_path / "workspace-git-backup"
    assert (backup / ".git" / "HEAD").is_file()
    alias = ws / "bin" / ".git-alias.sh"
    assert alias.is_file()
    assert "maicelium-git" in alias.read_text()


def test_separate_git_refuses_existing_backup(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    (ws / ".git").mkdir()
    backup = tmp_path / "workspace-git-backup"
    backup.mkdir()
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = separate_git.main(["separate_git.py"])

    out = buf.getvalue()
    assert rc == 1
    assert "Backup directory already exists" in out


# ────────────────────────────────────────────────────────────────────────────
# BUG-01 regression: blank lines inside an entry must not survive removal
# ────────────────────────────────────────────────────────────────────────────


@requires_symlink
def test_remove_project_preserves_following_entry_with_blank_line(tmp_path, monkeypatch):
    """Removing 'alpha' must not leave orphaned indented lines from its block.

    WORKSPACE.md has a blank line inside the alpha entry (between 'path:' and
    'added:').  After removal only the beta entry must remain, with no orphaned
    '  added: 2024-01-01' line.
    """
    ws = _bootstrap_workspace(tmp_path)
    repo_alpha = _make_fake_project(tmp_path, "alpha_repo")
    repo_beta = _make_fake_project(tmp_path, "beta_repo")
    _patch_root(monkeypatch, ws)

    # Seed WORKSPACE.md with a blank line *inside* the alpha entry block.
    wf = ws / "WORKSPACE.md"
    wf.write_text(
        "# Active workspace\n"
        "projects:\n"
        "- name: alpha\n"
        "  path: /a\n"
        "\n"
        "  added: 2024-01-01\n"
        "- name: beta\n"
        "  path: /b\n"
    )

    # Create the symlink so remove_project accepts the request.
    (ws / "projects").mkdir(exist_ok=True)
    os.symlink(str(repo_alpha), str(ws / "projects" / "alpha"))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = remove_project.main(["remove_project.py", "alpha"])

    assert rc == 0, buf.getvalue()

    content = wf.read_text()
    assert "- name: alpha" not in content
    # The orphan line that was previously left behind.
    assert "  added: 2024-01-01" not in content
    # The beta entry must be fully intact.
    assert "- name: beta" in content
    assert "  path: /b" in content


# ────────────────────────────────────────────────────────────────────────────
# BUG-03 regression: separate_git cleans empty backup on move failure
# ────────────────────────────────────────────────────────────────────────────


def test_separate_git_cleans_backup_on_move_failure(tmp_path, monkeypatch):
    """When shutil.move raises, the empty backup directory must be removed.

    Without the fix, the backup dir is left empty and a subsequent invocation
    refuses to run ("Backup directory already exists"), creating an
    unrecoverable state without manual intervention.
    """
    ws = _bootstrap_workspace(tmp_path)
    (ws / "bin").mkdir()
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    _patch_root(monkeypatch, ws)

    # Make shutil.move fail unconditionally.
    monkeypatch.setattr(shutil, "move", lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated move failure")))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = separate_git.main(["separate_git.py"])

    assert rc == 1, buf.getvalue()

    backup = tmp_path / "workspace-git-backup"
    # The backup directory must have been cleaned up.
    assert not backup.exists(), (
        f"Empty backup dir was not removed after failed move: {backup}"
    )
    # The original .git must still be intact.
    assert (ws / ".git" / "HEAD").is_file(), ".git was lost despite failed move"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ────────────────────────────────────────────────────────────────────────────
# .claude/skills/ reflection (Claude Code native skill discovery)
# ────────────────────────────────────────────────────────────────────────────


@requires_symlink
def test_add_project_imports_skills_into_claude_skills(tmp_path, monkeypatch):
    """A plugged-in project's skills must land in .claude/skills/ too, so Claude
    Code registers them natively instead of relying on the operator to browse
    mesh/ by hand."""
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "demo", str(repo)])

    assert rc == 0, buf.getvalue()

    claude_link = ws / ".claude" / "skills" / "demo--myskill"
    assert claude_link.is_symlink(), (
        ".claude/skills/demo--myskill missing — project skills are not "
        "registered for Claude Code"
    )
    assert (claude_link / "SKILL.md").is_file()


@requires_symlink
def test_remove_project_prunes_claude_skills(tmp_path, monkeypatch):
    """Unplugging must prune .claude/skills/<name>--*.

    The link points at the real repo, which still exists on disk, so it never
    goes dangling — sync's broken-symlink cleanup would not catch it. Without
    an explicit prune the unplugged project's skills stay registered in Claude
    Code forever.
    """
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        add_project.main(["add_project.py", "demo", str(repo)])
        assert (ws / ".claude" / "skills" / "demo--myskill").is_symlink()
        rc = remove_project.main(["remove_project.py", "demo"])

    assert rc == 0, buf.getvalue()
    assert not os.path.lexists(str(ws / ".claude" / "skills" / "demo--myskill")), (
        "unplugged project skill still registered under .claude/skills/"
    )
    # The real repo must be untouched.
    assert (repo / ".cursor" / "skills" / "myskill" / "SKILL.md").is_file()


@requires_symlink
def test_add_project_code_only_skips_claude_skills(tmp_path, monkeypatch):
    """--code-only must not register skills in .claude/skills/ either."""
    ws = _bootstrap_workspace(tmp_path)
    repo = _make_fake_project(tmp_path, "fakeproj")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = add_project.main(["add_project.py", "--code-only", "demo", str(repo)])

    assert rc == 0
    assert not (ws / ".claude" / "skills" / "demo--myskill").exists()
