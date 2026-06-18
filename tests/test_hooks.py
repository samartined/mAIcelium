"""Tests for Python PreToolUse hooks (guard_bash.py / guard_write.py)."""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_BASH = os.path.join(REPO_ROOT, "bin", "hooks", "guard_bash.py")
GUARD_WRITE = os.path.join(REPO_ROOT, "bin", "hooks", "guard_write.py")

from _marks import requires_symlink  # noqa: E402


def _run_hook(hook_path, payload, env=None, cwd=None):
    """Invoke a hook with a JSON payload on stdin and capture the result."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, hook_path],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=run_env,
        cwd=cwd,
    )


def _is_block(result):
    """Return True if hook produced a block decision."""
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return decoded.get("decision") == "block"


# ---------------------------------------------------------------------------
# guard_bash.py
# ---------------------------------------------------------------------------


def test_guard_bash_allows_safe_ls():
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "ls -la"}})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_bash_blocks_rm_rf_root():
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf /"}})
    assert result.returncode == 0
    assert _is_block(result)
    decoded = json.loads(result.stdout)
    assert "root" in decoded["reason"].lower() or "home" in decoded["reason"].lower()


def test_guard_bash_blocks_rm_rf_home():
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf ~"}})
    assert _is_block(result)


def test_guard_bash_allows_rm_rf_node_modules():
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "rm -rf node_modules"}}
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_bash_blocks_drop_table():
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": 'psql -c "DROP TABLE users"'}}
    )
    assert _is_block(result)


def test_guard_bash_blocks_force_push_main():
    result = _run_hook(
        GUARD_BASH,
        {"tool_input": {"command": "git push --force origin main"}},
    )
    assert _is_block(result)


def test_guard_bash_allows_force_push_branch():
    result = _run_hook(
        GUARD_BASH,
        {"tool_input": {"command": "git push --force origin feat/x"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_bash_blocks_chmod_777():
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "chmod 777 secret.sh"}}
    )
    assert _is_block(result)


def test_guard_bash_blocks_terraform_without_tfswitch():
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "terraform apply"}}
    )
    assert _is_block(result)


def test_guard_bash_allows_terraform_with_tfswitch():
    result = _run_hook(
        GUARD_BASH,
        {"tool_input": {"command": "tfswitch && terraform apply"}},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# guard_write.py
# ---------------------------------------------------------------------------


def test_guard_write_allows_normal_file(tmp_path):
    target = tmp_path / "src" / "main.py"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_write_blocks_env(tmp_path):
    target = tmp_path / ".env"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_env_local(tmp_path):
    target = tmp_path / ".env.local"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_git_internals(tmp_path):
    target = tmp_path / ".git" / "HEAD"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_workspace_md(tmp_path):
    target = tmp_path / "WORKSPACE.md"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_settings_json(tmp_path):
    target = tmp_path / ".claude" / "settings.json"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_cursor_folder(tmp_path):
    target = tmp_path / ".cursor" / "foo"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_lockfile(tmp_path):
    target = tmp_path / "package-lock.json"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_stale_layer_reflection(tmp_path):
    """A real file under mesh/skills/_common/ (not a symlink to a layer) must
    be blocked so the agent edits the canonical layer file instead."""
    reflection_dir = tmp_path / "mesh" / "skills" / "_common" / "foo"
    reflection_dir.mkdir(parents=True)
    target = reflection_dir / "SKILL.md"
    target.write_text("stale content\n")
    # layers root exists but the reflection is NOT a symlink to it
    (tmp_path / "mesh" / "layers").mkdir(parents=True, exist_ok=True)

    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)
    decoded = json.loads(result.stdout)
    assert "layer" in decoded["reason"].lower()


@requires_symlink
def test_guard_write_allows_layer_symlink(tmp_path):
    """A reflection that is a symlink resolving inside mesh/layers/ must be
    allowed (edits transparently reach the source of truth)."""
    # Canonical source-of-truth file inside a layer
    canonical_dir = (
        tmp_path / "mesh" / "layers" / "test-layer" / "skills" / "_common" / "foo"
    )
    canonical_dir.mkdir(parents=True)
    canonical = canonical_dir / "SKILL.md"
    canonical.write_text("canonical content\n")

    # Reflection: a symlink pointing at the canonical file
    reflection_dir = tmp_path / "mesh" / "skills" / "_common" / "foo"
    reflection_dir.mkdir(parents=True)
    reflection = reflection_dir / "SKILL.md"
    os.symlink(canonical, reflection)

    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(reflection)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_write_blocks_absolute_path_outside_workspace(tmp_path):
    """Fail-CLOSED on absolute paths that resolve outside the workspace root."""
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": "/etc/passwd"}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)
    assert "outside the workspace" in result.stdout.lower()


def test_guard_write_blocks_dotdot_traversal(tmp_path):
    """A relative path that escapes the workspace via .. must be blocked."""
    sub = tmp_path / "sub"
    sub.mkdir()
    escaping = str(sub / ".." / ".." / ".." / "etc" / "shadow")
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": escaping}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)
    assert "outside the workspace" in result.stdout.lower()


def test_guard_write_blocks_cross_drive_via_value_error(tmp_path, monkeypatch):
    """Simulate os.path.relpath raising ValueError (Windows cross-drive)
    by feeding a path on a separate root and verify fail-CLOSED behaviour."""
    # On POSIX, os.path.relpath does not raise; we exercise the equivalent
    # branch by giving an absolute path that does not start with root_real.
    # This reproduces the security guarantee: any file_path the hook cannot
    # safely relate to the workspace must be blocked, not allowed.
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": "/var/log/auth.log"}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_allows_claude_plans_dir(tmp_path):
    """Claude Code's own plan dir (~/.claude/plans/) is outside the workspace
    but legitimate harness state -- it must be allowed, not blocked."""
    home = tmp_path / "home"
    plans = home / ".claude" / "plans"
    plans.mkdir(parents=True)
    target = plans / "some-plan.md"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path / "workspace"), "HOME": str(home), "USERPROFILE": str(home)},  # Windows uses USERPROFILE, not HOME
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_guard_write_still_blocks_global_claude_settings(tmp_path):
    """The exception is scoped to plans/ only: the global ~/.claude/settings.json
    stays protected as out-of-workspace."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    target = claude / "settings.json"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path / "workspace"), "HOME": str(home), "USERPROFILE": str(home)},  # Windows uses USERPROFILE, not HOME
    )
    assert _is_block(result)


# ---------------------------------------------------------------------------
# guard_bash.py — TR-7: hardened rm -rf coverage
# ---------------------------------------------------------------------------

# --- BYPASS cases: these must all be BLOCKED ---


def test_guard_bash_blocks_rm_rf_home_user():
    """rm -rf /home/user — exact user home directory must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf /home/user"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_etc():
    """rm -rf /etc — system config root must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf /etc"}})
    assert _is_block(result)


# Loop-style test: each protected system root must be blocked individually
import pytest

@pytest.mark.parametrize("path", [
    "/usr", "/var", "/bin", "/lib", "/boot", "/root",
    "/sys", "/proc", "/dev", "/opt", "/srv", "/sbin",
])
def test_guard_bash_blocks_rm_rf_protected_roots(path):
    """rm -rf on any protected system root must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": f"rm -rf {path}"}})
    assert _is_block(result), f"Expected block for: rm -rf {path}"


def test_guard_bash_blocks_rm_rf_dotdot():
    """rm -rf .. — parent directory operand must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf .."}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_dot():
    """rm -rf . — current directory operand must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf ."}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_bare_star():
    """rm -rf * — bare wildcard must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf *"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_dot_slash_star():
    """rm -rf ./* — dot-slash wildcard must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf ./*"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_fr_etc():
    """rm -fr /etc — flag-order variant must be caught."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -fr /etc"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_dashdash_etc():
    """rm -rf -- /etc — with explicit -- separator must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf -- /etc"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_single_quoted_etc():
    """rm -rf '/etc' — single-quoted operand must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf '/etc'"}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_double_quoted_home_user():
    """rm -rf "/home/user" — double-quoted user home must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": 'rm -rf "/home/user"'}})
    assert _is_block(result)


def test_guard_bash_blocks_rm_rf_extra_spaces():
    """rm  -rf   /etc — extra whitespace (normalised by hook) must be blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm  -rf   /etc"}})
    assert _is_block(result)


def test_guard_bash_blocks_cd_root_then_rm_rf_star():
    """cd / && rm -rf * — blocked as a side-effect of the bare-* rule.
    NOTE: this is NOT cwd tracking; it matches because '*' alone is blocked
    regardless of the preceding cd.  The documented gap is 'cd /etc && rm -rf foo'
    (a non-wildcard relative operand after a cd).
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "cd / && rm -rf *"}}
    )
    assert _is_block(result)


# --- NEGATIVE cases: these must all be ALLOWED (not blocked) ---


def test_guard_bash_allows_git_rm_rf_src():
    """git rm -rf src — most important: must never be falsely blocked."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "git rm -rf src"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_node_modules_negative():
    """rm -rf node_modules — standard cleanup, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf node_modules"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_dot_build():
    """rm -rf ./build — relative build dir, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf ./build"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_dist_star():
    """rm -rf dist/* — dist glob, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf dist/*"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_tmp_foo():
    """rm -rf /tmp/foo — /tmp subpath, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf /tmp/foo"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_build_cache():
    """rm -rf build/cache — relative build subdir, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf build/cache"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_rm_rf_target():
    """rm -rf target — Maven/Cargo build dir, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "rm -rf target"}})
    assert result.returncode == 0
    assert not _is_block(result)


def test_guard_bash_allows_ls_la_negative():
    """ls -la — safe command, must be allowed."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": "ls -la"}})
    assert result.returncode == 0
    assert not _is_block(result)


# --- KNOWN-GAP cases: document best-effort limits (assert NOT blocked) ---


def test_guard_bash_known_gap_variable_indirection():
    """Documented best-effort gap; real boundary is write-scope + human review.

    T=/etc; rm -rf $T uses variable indirection invisible to the raw-string
    regex.  The hook does NOT catch this — by design and documented.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "T=/etc; rm -rf $T"}}
    )
    assert not _is_block(result), (
        "Known gap: variable indirection is not blocked (best-effort limit)"
    )


def test_guard_bash_known_gap_command_substitution():
    """Documented best-effort gap; real boundary is write-scope + human review.

    rm -rf $(echo /etc) uses command substitution invisible to the raw-string
    regex.  The hook does NOT catch this — by design and documented.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "rm -rf $(echo /etc)"}}
    )
    assert not _is_block(result), (
        "Known gap: command substitution is not blocked (best-effort limit)"
    )


def test_guard_bash_known_gap_cd_then_rm_rf_foo():
    """Documented best-effort gap; real boundary is write-scope + human review.

    cd /etc && rm -rf foo changes cwd so 'foo' resolves to /etc/foo, but the
    hook cannot track cwd.  The hook does NOT catch this — by design and documented.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "cd /etc && rm -rf foo"}}
    )
    assert not _is_block(result), (
        "Known gap: cwd-based resolution is not tracked (best-effort limit)"
    )


def test_guard_bash_known_gap_xargs():
    """Documented best-effort gap; real boundary is write-scope + human review.

    echo /etc | xargs rm -rf pipes the operand; the hook only sees 'rm -rf'
    with no inline operand.  Not blocked — by design and documented.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "echo /etc | xargs rm -rf"}}
    )
    assert not _is_block(result), (
        "Known gap: piped xargs operands are not blocked (best-effort limit)"
    )


def test_guard_bash_known_gap_find_delete():
    """Documented best-effort gap; real boundary is write-scope + human review.

    find /etc -delete achieves deletion without using rm at all.
    Not blocked — by design and documented.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "find /etc -delete"}}
    )
    assert not _is_block(result), (
        "Known gap: find -delete is not covered by the rm guard (best-effort limit)"
    )


# --- FAIL-OPEN test ---


def test_guard_bash_fail_open_malformed_json():
    """Malformed/non-JSON stdin must exit 0 (fail-open), not crash or block."""
    import subprocess
    result = subprocess.run(
        [__import__("sys").executable, GUARD_BASH],
        input="THIS IS NOT JSON",
        capture_output=True,
        text=True,
        timeout=10,
        env=__import__("os").environ.copy(),
    )
    assert result.returncode == 0
    # Must NOT produce a block decision
    assert not _is_block(result)
