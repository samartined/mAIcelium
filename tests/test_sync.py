"""Tests for bin/sync_symlinks.py — Python port of bin/sync_symlinks.sh.

Each test builds a minimal workspace under tmp_path and exercises a single
behavior of the planner+executor: rule mirroring, drift detection, relative
symlinks, dry-run, check-only, broken-symlink cleanup, action-plan purity.
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import sync_symlinks  # noqa: E402

from _marks import requires_symlink


def _write(path, content):
    """Write a text file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _bootstrap_workspace(tmp_path):
    """Create a minimal real workspace under tmp_path matching layout assumptions."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "mesh").mkdir()
    (ws / "mesh" / "skills").mkdir()
    (ws / "mesh" / "skills" / "_common").mkdir()
    (ws / "mesh" / "skills" / "_domains").mkdir()
    (ws / "mesh" / "skills" / "_clients").mkdir()
    (ws / "mesh" / "rules").mkdir()
    (ws / "mesh" / "rules" / "_clients").mkdir()
    (ws / "mesh" / "commands").mkdir()
    (ws / "mesh" / "layers").mkdir()
    (ws / "projects").mkdir()
    (ws / ".cursor").mkdir()
    (ws / ".cursor" / "rules").mkdir()
    (ws / ".cursor" / "skills-cursor").mkdir()
    (ws / ".agents").mkdir()
    (ws / ".agents" / "rules").mkdir()
    (ws / ".agents" / "skills").mkdir()
    (ws / ".agents" / "workflows").mkdir()
    _write(
        str(ws / "mesh" / "conventions.json"),
        json.dumps({
            "project_data_dir": ".cursor",
            "project_data_subdirs": ["plans", "bitacora", "config", "agents", "docs"],
            "project_rules_subdir": "rules",
            "project_skills_subdirs": ["skills", "skills-cursor"],
        }),
    )
    return ws


def _patch_root(monkeypatch, workspace):
    """Force resolve_root to return our temp workspace."""
    ws_str = str(workspace)
    monkeypatch.setattr(sync_symlinks, "resolve_root", lambda: ws_str)


# ── Test 1: empty workspace ────────────────────────────────────────────────


def test_sync_empty_workspace(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0, buf.getvalue()
    assert (ws / ".mcp.json").is_file()
    assert (ws / "mAIcelium.code-workspace").is_file()


# ── Test 2: rules become relative symlinks ─────────────────────────────────


@requires_symlink
def test_sync_creates_rule_symlinks(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "global content\n")
    _write(str(ws / "mesh" / "rules" / "conventions.mdc"), "conv content\n")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0
    g = ws / ".cursor" / "rules" / "global.mdc"
    c = ws / ".cursor" / "rules" / "conventions.mdc"
    assert g.is_symlink()
    assert c.is_symlink()
    # Target must be relative (NOT absolute)
    assert not os.path.isabs(os.readlink(str(g)))
    assert not os.path.isabs(os.readlink(str(c)))
    # And resolves to the actual mesh file
    assert os.path.realpath(str(g)) == os.path.realpath(str(ws / "mesh" / "rules" / "global.mdc"))


# ── Test 3: dry-run leaves filesystem unchanged ────────────────────────────


def _snapshot_listing(path):
    """Return a sorted list of (relpath, is_symlink, link_target_or_size) tuples."""
    out = []
    for root, dirs, files in os.walk(path):
        # Walk visits the directory entry too; we capture both dirs and files.
        for name in list(dirs) + files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, path)
            if os.path.islink(full):
                out.append((rel, True, os.readlink(full)))
            elif os.path.isfile(full):
                out.append((rel, False, os.path.getsize(full)))
            else:
                out.append((rel, False, "dir"))
    return sorted(out)


def test_sync_dry_run_no_changes(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "global content\n")
    _patch_root(monkeypatch, ws)

    before = _snapshot_listing(str(ws))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main(["--dry-run"])

    assert rc == 0
    after = _snapshot_listing(str(ws))
    assert before == after, "dry-run must not modify the filesystem"


# ── Test 4: check-only returns 0 when no drift ─────────────────────────────


def test_sync_check_only_no_drift_returns_0(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "global content\n")
    _patch_root(monkeypatch, ws)

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = sync_symlinks.main(["--check-only"])

    assert rc == 0, buf_err.getvalue()


# ── Test 5: drift detection (identical content) ────────────────────────────


@requires_symlink
def test_sync_drift_detection_identical(tmp_path, monkeypatch):
    """Replace a layer-managed reflection with real content equal to the layer's.
    Without --fix-drift: drift reported. With --fix-drift: replaced by symlink."""
    ws = _bootstrap_workspace(tmp_path)

    # Build an external layer with a _common skill called "foo".
    layer = tmp_path / "ext_layer"
    layer.mkdir()
    (layer / "skills").mkdir()
    (layer / "skills" / "_common").mkdir()
    skill_dir = layer / "skills" / "_common" / "foo"
    skill_dir.mkdir()
    _write(str(skill_dir / "SKILL.md"), "foo skill body\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: testlayer\n"
        f"    path: {layer}\n",
    )

    # Now manually drop a real copy of the skill content at the mesh reflection
    # path (where a symlink would normally go).
    reflection = ws / "mesh" / "skills" / "_common" / "foo"
    reflection.mkdir()
    _write(str(reflection / "SKILL.md"), "foo skill body\n")

    _patch_root(monkeypatch, ws)

    # First: check-only without --fix-drift must return 1 and report identical.
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = sync_symlinks.main(["--check-only"])

    assert rc == 1
    assert "identical" in buf_err.getvalue()
    assert "foo" in buf_err.getvalue()
    # Still a real directory (untouched)
    assert reflection.is_dir() and not reflection.is_symlink()

    # Second: with --fix-drift, the real dir gets replaced by a symlink.
    buf_out2 = io.StringIO()
    with redirect_stdout(buf_out2):
        rc2 = sync_symlinks.main(["--fix-drift"])

    assert rc2 == 0
    assert reflection.is_symlink()


# ── Test 6: drift detection (divergent content) ────────────────────────────


def test_sync_drift_detection_divergent(tmp_path, monkeypatch):
    """Replace a reflection with DIVERGENT real content. Drift must be reported
    and the reflection never modified (even with --fix-drift)."""
    ws = _bootstrap_workspace(tmp_path)
    layer = tmp_path / "ext_layer"
    layer.mkdir()
    (layer / "skills" / "_common" / "bar").mkdir(parents=True)
    _write(str(layer / "skills" / "_common" / "bar" / "SKILL.md"), "layer content\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: testlayer\n"
        f"    path: {layer}\n",
    )

    reflection = ws / "mesh" / "skills" / "_common" / "bar"
    reflection.mkdir()
    _write(str(reflection / "SKILL.md"), "DIFFERENT content\n")

    _patch_root(monkeypatch, ws)

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = sync_symlinks.main(["--check-only"])

    assert rc == 1
    assert "divergent" in buf_err.getvalue()

    # Even with --fix-drift, divergent stays untouched.
    buf_out2 = io.StringIO()
    with redirect_stdout(buf_out2):
        rc2 = sync_symlinks.main(["--fix-drift"])

    # Reflection still a real directory (not a symlink).
    assert reflection.is_dir()
    assert not reflection.is_symlink()
    # Body must still hold the DIFFERENT content.
    assert (reflection / "SKILL.md").read_text() == "DIFFERENT content\n"
    # Exit code 0 (divergent does not abort), but drift was reported in output.
    assert rc2 == 0


# ── Test 7: produced symlinks are relative ─────────────────────────────────


@requires_symlink
def test_sync_relative_symlinks(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "alpha.mdc"), "a\n")
    skill_dir = ws / "mesh" / "skills" / "_common" / "myskill"
    skill_dir.mkdir(parents=True)
    _write(str(skill_dir / "SKILL.md"), "body\n")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0

    rule_link = ws / ".cursor" / "rules" / "alpha.mdc"
    assert rule_link.is_symlink()
    assert not os.path.isabs(os.readlink(str(rule_link)))

    skill_link = ws / ".cursor" / "skills-cursor" / "myskill"
    assert skill_link.is_symlink()
    assert not os.path.isabs(os.readlink(str(skill_link)))


# ── Test 8: broken symlinks are cleaned ────────────────────────────────────


@requires_symlink
def test_sync_clean_broken_symlinks(tmp_path, monkeypatch):
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "good.mdc"), "good\n")

    # Pre-create a dangling symlink in .cursor/rules/.
    dangling = ws / ".cursor" / "rules" / "dangling.mdc"
    os.symlink("/nonexistent/path/somewhere", str(dangling))
    assert dangling.is_symlink()
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0
    # Broken symlink cleaned up; good rule symlink created.
    assert not dangling.exists()
    assert not dangling.is_symlink()
    assert (ws / ".cursor" / "rules" / "good.mdc").is_symlink()


# ── Test 9: planner / executor separation ──────────────────────────────────


def test_sync_action_plan_separation(tmp_path):
    """plan_actions returns Action dataclasses with no side effects;
    execute(dry_run=True) also has no side effects."""
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "g\n")

    before = _snapshot_listing(str(ws))

    conventions = sync_symlinks.load_conventions(str(ws))
    layers = sync_symlinks.load_workspace_section(str(ws), "mesh_layers")
    mcp_source = sync_symlinks.load_workspace_section(str(ws), "mcp_source")

    actions = sync_symlinks.plan_actions(
        str(ws), conventions, layers, mcp_source, fix_drift=False,
    )

    after_plan = _snapshot_listing(str(ws))
    assert before == after_plan, "plan_actions must have no side effects"

    assert isinstance(actions, list)
    assert len(actions) > 0
    for a in actions:
        assert isinstance(a, sync_symlinks.Action)
        assert isinstance(a.kind, str)

    # execute with dry_run is also a no-op.
    buf = io.StringIO()
    with redirect_stdout(buf):
        sync_symlinks.execute(actions, dry_run=True)
    after_dry = _snapshot_listing(str(ws))
    assert before == after_dry, "execute(dry_run=True) must have no side effects"


# ── Test 10: empty section marker triggers degraded exit code ──────────────


def test_sync_workspace_md_warning_on_empty_section_marker(tmp_path, monkeypatch, capsys):
    """WORKSPACE.md with mesh_layers: marker but no layers + non-empty file
    must emit warning to stderr AND return exit code 3 (degraded)."""
    ws = _bootstrap_workspace(tmp_path)
    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n\nprojects:\n  - name: x\n    path: /x\n",
    )
    _patch_root(monkeypatch, ws)

    rc = sync_symlinks.main([])
    captured = capsys.readouterr()

    assert rc == 3
    assert "parser returned empty" in captured.err


# ── Test 11: mesh skills reflect into .claude/skills/ (Claude Code native) ──


@requires_symlink
def test_sync_reflects_mesh_skills_into_claude_skills(tmp_path, monkeypatch):
    """Every mesh skill bucket must land in .claude/skills/ with the same flat
    naming used for Cursor and Antigravity, via RELATIVE symlinks.

    Without this, mesh skills are invisible to Claude Code's native skill
    discovery, which scans .claude/skills/<name>/SKILL.md.
    """
    ws = _bootstrap_workspace(tmp_path)

    # Native (flat) skill, requires SKILL.md to be picked up
    native = ws / "mesh" / "skills" / "native-skill"
    native.mkdir(parents=True)
    _write(str(native / "SKILL.md"), "native\n")
    # _common
    common = ws / "mesh" / "skills" / "_common" / "common-skill"
    common.mkdir(parents=True)
    _write(str(common / "SKILL.md"), "common\n")
    # _domains, nested form -> <domain>--<skill>
    nested = ws / "mesh" / "skills" / "_domains" / "devops" / "terraform"
    nested.mkdir(parents=True)
    _write(str(nested / "SKILL.md"), "tf\n")
    # _clients -> <client>--<skill>
    client = ws / "mesh" / "skills" / "_clients" / "tiber" / "jira-workflow"
    client.mkdir(parents=True)
    _write(str(client / "SKILL.md"), "jira\n")

    _patch_root(monkeypatch, ws)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])
    assert rc == 0

    claude_skills = ws / ".claude" / "skills"
    expected = [
        "native-skill",
        "common-skill",
        "devops--terraform",
        "tiber--jira-workflow",
    ]
    for name in expected:
        link = claude_skills / name
        assert link.is_symlink(), f".claude/skills/{name} is not a symlink"
        assert (link / "SKILL.md").is_file(), f".claude/skills/{name} does not resolve"
        assert not os.path.isabs(os.readlink(str(link))), (
            f".claude/skills/{name} must be a relative symlink "
            f"(sync_symlinks invariant), got {os.readlink(str(link))}"
        )

    # Parity: the same set must exist in the other two dotfolders.
    for name in expected:
        assert (ws / ".cursor" / "skills-cursor" / name).is_symlink()
        assert (ws / ".agents" / "skills" / name).is_symlink()


@requires_symlink
def test_sync_cleans_broken_symlinks_in_claude_skills(tmp_path, monkeypatch):
    """A dangling link under .claude/skills/ (skill removed from a layer) must
    be pruned, exactly as in .cursor/skills-cursor/ and .agents/skills/."""
    ws = _bootstrap_workspace(tmp_path)
    claude_skills = ws / ".claude" / "skills"
    claude_skills.mkdir(parents=True)
    os.symlink(str(ws / "mesh" / "skills" / "_common" / "gone"),
               str(claude_skills / "gone"))
    assert os.path.islink(str(claude_skills / "gone"))

    _patch_root(monkeypatch, ws)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0
    assert not os.path.lexists(str(claude_skills / "gone")), (
        "broken symlink under .claude/skills/ was not cleaned"
    )


@requires_symlink
def test_sync_claude_skills_never_touches_home(tmp_path, monkeypatch):
    """The reflection must stay workspace-local: nothing is written to
    ~/.claude/skills/, which would leak workspace skills into every project."""
    ws = _bootstrap_workspace(tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    common = ws / "mesh" / "skills" / "_common" / "some-skill"
    common.mkdir(parents=True)
    _write(str(common / "SKILL.md"), "body\n")

    _patch_root(monkeypatch, ws)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])

    assert rc == 0
    assert (ws / ".claude" / "skills" / "some-skill").is_symlink()
    assert not (fake_home / ".claude" / "skills").exists(), (
        "sync must not create ~/.claude/skills/ — the reflection is workspace-local"
    )
