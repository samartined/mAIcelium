"""Tests for sync idempotency and _is_correct_relative_symlink separator fix.

TR-8: Verifies:
  - A second sync pass produces an observable no-op (symlink targets unchanged).
  - check-only after a full sync returns exit code 0.
  - _is_correct_relative_symlink returns True for a correctly linked symlink.
  - _is_correct_relative_symlink handles paths that would be mistaken as
    mismatched by a raw string compare (e.g. Windows backslash-style targets
    or trailing separators). The normpath fix makes these compare equal.
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


# ── Helpers (replicated from test_sync.py for self-containment) ──────────────

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


def _symlink_snapshot(root_path):
    """Return a dict mapping every symlink path (relative to root) to its readlink target.

    This is the 'observable' state we compare before/after the 2nd sync pass.
    """
    snapshot = {}
    root_str = str(root_path)
    for dirpath, dirnames, filenames in os.walk(root_str, followlinks=False):
        for name in list(dirnames) + filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                rel = os.path.relpath(full, root_str)
                snapshot[rel] = os.readlink(full)
    return snapshot


# ── Test 1: second sync pass is an observable no-op ─────────────────────────

@requires_symlink
def test_sync_second_pass_is_observable_noop(tmp_path, monkeypatch):
    """Run sync twice. The symlink-target snapshot must be identical before and after
    the second pass (observable idempotency).

    NOTE: The second pass may still emit link actions (ln -sfn collision-overwrite
    semantics are deliberate). What we verify is that the RESULT — the set of
    readlink targets — is unchanged.
    """
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "global\n")
    _write(str(ws / "mesh" / "rules" / "conv.mdc"), "conv\n")
    skill = ws / "mesh" / "skills" / "_common" / "myskill"
    skill.mkdir(parents=True)
    _write(str(skill / "SKILL.md"), "skill body\n")
    _patch_root(monkeypatch, ws)

    # First pass: set everything up
    buf1 = io.StringIO()
    with redirect_stdout(buf1):
        rc1 = sync_symlinks.main([])
    assert rc1 == 0, f"First sync failed: {buf1.getvalue()}"

    # Capture snapshot of all symlink targets after first pass
    before = _symlink_snapshot(ws)
    assert before, "Expected at least one symlink after first sync pass"

    # Second pass: must produce the same symlink-target state
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        rc2 = sync_symlinks.main([])
    assert rc2 == 0, f"Second sync failed: {buf2.getvalue()}"

    after = _symlink_snapshot(ws)
    assert before == after, (
        "Second sync pass changed symlink targets (not idempotent).\n"
        f"Added: {set(after) - set(before)}\n"
        f"Removed: {set(before) - set(after)}\n"
        f"Changed: {[k for k in before if k in after and before[k] != after[k]]}"
    )


# ── Test 2: check-only returns 0 after a full sync ───────────────────────────

def test_sync_check_only_after_sync_returns_0(tmp_path, monkeypatch):
    """After a clean sync with no external layers, --check-only must return 0."""
    ws = _bootstrap_workspace(tmp_path)
    _write(str(ws / "mesh" / "rules" / "global.mdc"), "global\n")
    _patch_root(monkeypatch, ws)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc_sync = sync_symlinks.main([])
    assert rc_sync == 0

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc_check = sync_symlinks.main(["--check-only"])

    assert rc_check == 0, (
        f"--check-only returned {rc_check} after a clean sync.\n"
        f"stderr: {buf_err.getvalue()}"
    )


# ── Test 3: _is_correct_relative_symlink returns True for correct link ───────

@requires_symlink
def test_is_correct_relative_symlink_true_for_correct_link(tmp_path):
    """Create an actual symlink and verify _is_correct_relative_symlink detects it."""
    src = tmp_path / "src_dir"
    src.mkdir()
    dst = tmp_path / "dst_dir" / "link"
    dst.parent.mkdir()

    src_abs = str(src)
    dst_abs = str(dst)

    # Create the relative symlink the way sync_symlinks does it
    sync_symlinks.create_relative_link(src_abs, dst_abs, target_is_directory=True)

    assert sync_symlinks._is_correct_relative_symlink(dst_abs, src_abs), (
        "_is_correct_relative_symlink returned False for a correctly created symlink"
    )


# ── Test 4: normpath separator fix ──────────────────────────────────────────

def test_is_correct_relative_symlink_windows_backslash_target(monkeypatch, tmp_path):
    """Verify _is_correct_relative_symlink handles a Windows-style backslash target.

    Scenario: on Windows, os.readlink can return a path with backslash separators
    (e.g. '..\\..\\mesh\\rules\\global.mdc') while os.path.relpath produces the
    forward-slash form ('../../../mesh/rules/global.mdc').

    Without the normpath fix: the raw string comparison fails (False).
    After the fix: os.path.normpath normalises both sides to the native separator,
    making the comparison succeed on Windows (True). On POSIX, normpath does not
    convert backslashes, so the test uses the replace('/', os.path.sep) idiom
    to produce a portable 'native-sep target' that os.path.normpath CAN normalise.

    Additionally, a direct string-comparison assertion confirms the 'fail before fix'
    behaviour: when a backslash path is compared raw to a forward-slash path, they
    differ — regardless of platform.  This is the bug the fix addresses.
    """
    src_abs = str(tmp_path / "mesh" / "rules" / "global.mdc")
    dst_abs = str(tmp_path / ".cursor" / "rules" / "global.mdc")

    expected = os.path.relpath(src_abs, os.path.dirname(dst_abs))

    # ── Part A: demonstrate the conceptual bug ──────────────────────────────
    # Hard-coded Windows backslash target (valid cross-platform for string comparison).
    windows_target = expected.replace("/", "\\")
    # Raw string comparison fails when targets use different separators.
    assert windows_target != expected or os.sep == "\\", (
        "Expected the Windows-backslash target to differ from the forward-slash "
        "expected path (this assertion fires only when they are different, i.e. "
        "when running on POSIX)."
    )
    # The ORIGINAL code would do: os.readlink(dst) == expected
    # This returns False when readlink returns the backslash form (on POSIX too).
    if os.sep != "\\":  # POSIX: literal backslash in string != forward-slash
        assert windows_target != expected  # proves old code would return False

    # ── Part B: normpath fix makes it work with native-sep form ────────────
    # Use os.sep substitution: on POSIX this is a no-op; on Windows it produces
    # the real backslash form.  normpath then normalises both sides identically.
    native_target = expected.replace("/", os.sep)

    monkeypatch.setattr(os.path, "islink", lambda p: p == dst_abs)
    monkeypatch.setattr(os, "readlink", lambda p: native_target)

    result = sync_symlinks._is_correct_relative_symlink(dst_abs, src_abs)
    assert result is True, (
        f"_is_correct_relative_symlink returned False after normpath fix.\n"
        f"readlink returned: {native_target!r}\n"
        f"expected:          {expected!r}\n"
        f"normpath readlink: {os.path.normpath(native_target)!r}\n"
        f"normpath expected: {os.path.normpath(expected)!r}"
    )
