"""Tests for mesh/commands/scripts/list_projects.py and project_health.py.

Uses subprocess invocation with MAICELIUM_ROOT env var pointing at a
temporary workspace, mirroring the idiom in test_hooks.py (_run_hook).
"""
import os
import subprocess
import sys

import pytest

from _marks import requires_symlink

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "mesh", "commands", "scripts")
_LIST_PROJECTS = os.path.join(_SCRIPTS_DIR, "list_projects.py")
_PROJECT_HEALTH = os.path.join(_SCRIPTS_DIR, "project_health.py")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_script(script_path, tmp_root, extra_env=None, encoding=None):
    """Run a command script with MAICELIUM_ROOT pointing at tmp_root."""
    env = os.environ.copy()
    env["MAICELIUM_ROOT"] = str(tmp_root)
    if extra_env:
        env.update(extra_env)
    kwargs = dict(
        args=[sys.executable, script_path],
        capture_output=True,
        timeout=15,
        env=env,
    )
    if encoding is not None:
        kwargs["text"] = True
        kwargs["encoding"] = encoding
        kwargs["errors"] = "replace"
    else:
        kwargs["text"] = True
        kwargs["encoding"] = "utf-8"
    return subprocess.run(**kwargs)


def _make_workspace(tmp_path):
    """Create a minimal tmp workspace directory (no projects/ yet)."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _make_workspace_with_empty_projects(tmp_path):
    """Create a workspace with an empty projects/ directory."""
    ws = _make_workspace(tmp_path)
    (ws / "projects").mkdir()
    return ws


# ── list_projects.py tests ───────────────────────────────────────────────────

def test_list_projects_honours_maicelium_root_no_projects_dir(tmp_path):
    """list_projects exits 0 and prints 'No projects directory found' when
    projects/ does not exist in MAICELIUM_ROOT workspace."""
    ws = _make_workspace(tmp_path)
    result = _run_script(_LIST_PROJECTS, ws)
    assert result.returncode == 0, result.stderr
    assert "No projects directory found" in result.stdout


def test_list_projects_empty_projects_dir(tmp_path):
    """list_projects exits 0 and prints 'No projects are currently linked'
    when projects/ exists but is empty."""
    ws = _make_workspace_with_empty_projects(tmp_path)
    result = _run_script(_LIST_PROJECTS, ws)
    assert result.returncode == 0, result.stderr
    assert "No projects are currently linked" in result.stdout


@requires_symlink
def test_list_projects_lists_linked_project(tmp_path):
    """list_projects shows a linked project name and its target."""
    ws = _make_workspace_with_empty_projects(tmp_path)
    # Create a target directory and symlink it under projects/
    target = tmp_path / "my-repo"
    target.mkdir()
    link = ws / "projects" / "my-repo"
    os.symlink(str(target), str(link))

    result = _run_script(_LIST_PROJECTS, ws)
    assert result.returncode == 0, result.stderr
    assert "my-repo" in result.stdout
    assert "linked project" in result.stdout


# ── project_health.py tests ──────────────────────────────────────────────────

def test_project_health_honours_maicelium_root_empty(tmp_path):
    """project_health exits 0 on a workspace with no projects/ directory."""
    ws = _make_workspace(tmp_path)
    result = _run_script(_PROJECT_HEALTH, ws)
    assert result.returncode == 0, result.stderr
    assert "Health Report" in result.stdout


def test_project_health_empty_projects_dir(tmp_path):
    """project_health reports 'No projects linked' when projects/ is empty."""
    ws = _make_workspace_with_empty_projects(tmp_path)
    result = _run_script(_PROJECT_HEALTH, ws)
    assert result.returncode == 0, result.stderr
    assert "No projects linked" in result.stdout


@requires_symlink
def test_project_health_reports_linked_project(tmp_path):
    """project_health lists a linked project with health indicators."""
    ws = _make_workspace_with_empty_projects(tmp_path)
    target = tmp_path / "my-repo"
    target.mkdir()
    link = ws / "projects" / "my-repo"
    os.symlink(str(target), str(link))

    result = _run_script(_PROJECT_HEALTH, ws)
    assert result.returncode == 0, result.stderr
    assert "my-repo" in result.stdout
    assert "Health Report" in result.stdout


# ── cp1252 / encoding tests ──────────────────────────────────────────────────
# These tests fail on origin/dev (Traceback: UnicodeEncodeError for emoji output)
# and pass after the _safe_stdout fix.

def test_list_projects_no_crash_on_cp1252_console(tmp_path):
    """list_projects must not crash with UnicodeEncodeError on a cp1252 console.

    Simulates Windows cp1252 I/O by setting PYTHONIOENCODING=cp1252.
    The script emits emoji characters (📭 etc.) that are not cp1252-encodable;
    without _safe_stdout() this causes UnicodeEncodeError.
    """
    ws = _make_workspace(tmp_path)
    result = _run_script(
        _LIST_PROJECTS, ws,
        extra_env={"PYTHONIOENCODING": "cp1252"},
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"list_projects crashed under cp1252.\nstderr: {result.stderr!r}"
    )
    assert "Traceback" not in result.stderr
    assert "UnicodeEncodeError" not in result.stderr


def test_project_health_no_crash_on_cp1252_console(tmp_path):
    """project_health must not crash with UnicodeEncodeError on a cp1252 console."""
    ws = _make_workspace(tmp_path)
    result = _run_script(
        _PROJECT_HEALTH, ws,
        extra_env={"PYTHONIOENCODING": "cp1252"},
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"project_health crashed under cp1252.\nstderr: {result.stderr!r}"
    )
    assert "Traceback" not in result.stderr
    assert "UnicodeEncodeError" not in result.stderr
