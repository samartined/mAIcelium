"""Tests for single-pass layer reflection fix (issue #27).

When a new skill or rule is added to a mounted mesh layer, a SINGLE call to
sync_symlinks.main([]) must materialize it into mesh/ AND reflect it into
.cursor/ and .agents/ in one shot.

Root cause (pre-fix): _plan_skills_for/_plan_rules_for enumerate mesh/ via
os.listdir at PLAN time, before _plan_layer_materialization's queued symlinks
have executed, so new entries were invisible to the reflection planners and a
second sync was required.

Fix (plan_phase1 + plan_phase2 execute-then-replan): main() executes phase 1
(mesh/ writers) first, then plans and executes phase 2 (outward reflectors),
so the reflection planners see the freshly-materialized mesh/ symlinks.

TR-8 invariants verified:
- Reflected symlink targets are the TWO-HOP form ../../mesh/skills/_common/<x>
  (via mesh), NOT a direct-to-layer target.
- A second full sync is an observable no-op (symlink-target snapshot unchanged).
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

from _marks import requires_symlink  # noqa: E402


# ── Shared helpers ────────────────────────────────────────────────────────────

def _write(path, content):
    """Write a text file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


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


def _symlink_snapshot(root_path):
    """Return a dict mapping every symlink path (relative to root) to its readlink target."""
    snapshot = {}
    root_str = str(root_path)
    for dirpath, dirnames, filenames in os.walk(root_str, followlinks=False):
        for name in list(dirnames) + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                rel = os.path.relpath(full, root_str)
                snapshot[rel] = os.readlink(full)
    return snapshot


def _make_external_layer(tmp_path, layer_name="testlayer"):
    """Return (layer_path, ws_workspace_md_snippet) for a minimal external layer."""
    layer = tmp_path / layer_name
    layer.mkdir()
    return layer


# ── Test 1: single-pass reflects a brand-new _common SKILL ──────────────────

@requires_symlink
def test_single_pass_reflects_layer_common_skill(tmp_path, monkeypatch):
    """Register an external layer with skills/_common/<newskill>/SKILL.md.

    Run sync_symlinks.main([]) ONCE. Assert that BOTH
      .cursor/skills-cursor/<newskill>  AND  .agents/skills/<newskill>
    are symlinks — without needing a second sync.

    This test FAILS on origin/dev (before the two-phase fix) and PASSES after.
    """
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_external_layer(tmp_path)

    # Populate layer: skills/_common/newskill/
    skill_dir = layer / "skills" / "_common" / "newskill"
    skill_dir.mkdir(parents=True)
    _write(str(skill_dir / "SKILL.md"), "# newskill\nBody.\n")

    # Register layer in WORKSPACE.md
    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: {layer.name}\n"
        f"    path: {layer}\n",
    )

    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])
    assert rc == 0, f"sync failed:\n{buf.getvalue()}"

    cursor_link = ws / ".cursor" / "skills-cursor" / "newskill"
    agents_link = ws / ".agents" / "skills" / "newskill"

    assert cursor_link.is_symlink(), (
        ".cursor/skills-cursor/newskill is not a symlink after a single sync — "
        "two-phase fix may not be in effect"
    )
    assert agents_link.is_symlink(), (
        ".agents/skills/newskill is not a symlink after a single sync — "
        "two-phase fix may not be in effect"
    )


# ── Test 2: single-pass reflects a brand-new _domains RULE ──────────────────

@requires_symlink
def test_single_pass_reflects_layer_domain_rule(tmp_path, monkeypatch):
    """Register an external layer with rules/_domains/<d>/<f>.mdc.

    Run sync_symlinks.main([]) ONCE. Assert that BOTH
      .cursor/rules/domain--<d>--<f>.mdc  AND  .agents/rules/domain--<d>--<f>.mdc
    are symlinks — without needing a second sync.

    This test FAILS on origin/dev (before the two-phase fix) and PASSES after.
    """
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_external_layer(tmp_path)

    # Populate layer: rules/_domains/backend/api.mdc
    rule_file = layer / "rules" / "_domains" / "backend" / "api.mdc"
    rule_file.parent.mkdir(parents=True)
    _write(str(rule_file), "# api rule\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: {layer.name}\n"
        f"    path: {layer}\n",
    )

    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])
    assert rc == 0, f"sync failed:\n{buf.getvalue()}"

    expected_name = "domain--backend--api.mdc"
    cursor_link = ws / ".cursor" / "rules" / expected_name
    agents_link = ws / ".agents" / "rules" / expected_name

    assert cursor_link.is_symlink(), (
        f".cursor/rules/{expected_name} is not a symlink after a single sync — "
        "two-phase fix may not be in effect (rules path)"
    )
    assert agents_link.is_symlink(), (
        f".agents/rules/{expected_name} is not a symlink after a single sync — "
        "two-phase fix may not be in effect (agents rules path)"
    )


# ── Test 3: two-hop target guard ─────────────────────────────────────────────

@requires_symlink
def test_reflected_layer_skill_uses_two_hop_target(tmp_path, monkeypatch):
    """The readlink target of a reflected layer skill must go via mesh/ (two hops).

    Expected form: ../../mesh/skills/_common/<x>  (not a direct path into the
    external layer).  This guards against an accidental Option-1 regression where
    the fix would short-circuit the mesh/ indirection.
    """
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_external_layer(tmp_path)

    skill_dir = layer / "skills" / "_common" / "guardskill"
    skill_dir.mkdir(parents=True)
    _write(str(skill_dir / "SKILL.md"), "# guardskill\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: {layer.name}\n"
        f"    path: {layer}\n",
    )

    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])
    assert rc == 0, f"sync failed:\n{buf.getvalue()}"

    cursor_link = str(ws / ".cursor" / "skills-cursor" / "guardskill")
    assert os.path.islink(cursor_link), "Expected a symlink at .cursor/skills-cursor/guardskill"

    raw_target = os.readlink(cursor_link)
    normalized = os.path.normpath(raw_target)

    # The two-hop path must pass through mesh/skills/_common/
    # e.g. ../../mesh/skills/_common/guardskill
    assert "mesh" in normalized and "skills" in normalized and "_common" in normalized, (
        f"Reflected symlink target does not go via mesh/skills/_common/.\n"
        f"readlink: {raw_target!r}\n"
        f"normpath: {normalized!r}\n"
        "If this fails, a direct-to-layer target was written (Option-1 regression)."
    )

    # Must NOT be an absolute path
    assert not os.path.isabs(raw_target), (
        f"Reflected symlink target is absolute (expected relative): {raw_target!r}"
    )


# ── Test 4: TR-8 idempotency with an external layer seeded ──────────────────

@requires_symlink
def test_tr8_idempotency_with_external_layer(tmp_path, monkeypatch):
    """Snapshot symlink targets after the 1st sync; run a 2nd; assert before==after.

    The two-phase split must not break TR-8: a second full sync must produce
    the same observable symlink-target state as the first.
    """
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_external_layer(tmp_path)

    skill_dir = layer / "skills" / "_common" / "idempskill"
    skill_dir.mkdir(parents=True)
    _write(str(skill_dir / "SKILL.md"), "# idempotency skill\n")

    rule_file = layer / "rules" / "_domains" / "ops" / "deploy.mdc"
    rule_file.parent.mkdir(parents=True)
    _write(str(rule_file), "# deploy rule\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: {layer.name}\n"
        f"    path: {layer}\n",
    )

    _patch_root(monkeypatch, ws)

    # First pass
    buf1 = io.StringIO()
    with redirect_stdout(buf1):
        rc1 = sync_symlinks.main([])
    assert rc1 == 0, f"First sync failed:\n{buf1.getvalue()}"

    before = _symlink_snapshot(ws)
    assert before, "Expected at least one symlink after first sync"

    # Second pass
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        rc2 = sync_symlinks.main([])
    assert rc2 == 0, f"Second sync failed:\n{buf2.getvalue()}"

    after = _symlink_snapshot(ws)
    assert before == after, (
        "Second sync changed symlink targets (TR-8 idempotency broken with external layer).\n"
        f"Added:   {set(after) - set(before)}\n"
        f"Removed: {set(before) - set(after)}\n"
        f"Changed: {[k for k in before if k in after and before[k] != after[k]]}"
    )


# ── Test: layer skills reach .claude/skills/ in a single pass ───────────────

@requires_symlink
def test_single_pass_reflects_layer_skills_into_claude_skills(tmp_path, monkeypatch):
    """A brand-new layer's skills must reach .claude/skills/ in ONE sync,
    for both the shared (_common) and client-scoped buckets.

    This is the case the framework used to miss entirely: layer skills were
    reflected for Cursor and Antigravity but never registered for Claude Code.
    """
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_external_layer(tmp_path)

    shared = layer / "skills" / "_common" / "newskill"
    shared.mkdir(parents=True)
    _write(str(shared / "SKILL.md"), "# newskill\nBody.\n")

    # Flat folder inside the layer -> client bucket -> <client>--<skill>
    scoped = layer / "skills" / "jira-workflow"
    scoped.mkdir(parents=True)
    _write(str(scoped / "SKILL.md"), "# jira-workflow\nBody.\n")

    _write(
        str(ws / "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: {layer.name}\n"
        f"    path: {layer}\n"
        "    client: tiber\n",
    )

    _patch_root(monkeypatch, ws)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = sync_symlinks.main([])
    assert rc == 0, f"sync failed:\n{buf.getvalue()}"

    claude_skills = ws / ".claude" / "skills"
    for name in ("newskill", "tiber--jira-workflow"):
        link = claude_skills / name
        assert link.is_symlink(), (
            f".claude/skills/{name} is not a symlink after a single sync"
        )
        assert (link / "SKILL.md").is_file(), (
            f".claude/skills/{name} does not resolve to the layer"
        )
        # Must resolve into the layer, not into a stale mesh/ copy.
        assert str(layer) in os.path.realpath(str(link))
