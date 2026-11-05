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


def _decision(result):
    """Return the hook's permissionDecision ("deny"/"ask"), or None (allow).

    A hook that exits non-zero is reported as "error" so tests can tell a
    crash (which Claude Code treats as non-blocking) from a real decision.
    """
    if result.returncode != 0:
        return "error"
    if not result.stdout.strip():
        return None
    decoded = json.loads(result.stdout)
    return decoded["hookSpecificOutput"]["permissionDecision"]


def _reason(result):
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def _is_block(result):
    """Return True if the hook denied the tool call."""
    return _decision(result) == "deny"


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
    reason = _reason(result).lower()
    assert "root" in reason or "home" in reason


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


def test_guard_bash_does_not_police_terraform_versions():
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "terraform apply"}}
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


def test_guard_write_asks_for_settings_json(tmp_path):
    """The agent's own settings are not silently writable: Edgar confirms."""
    target = tmp_path / ".claude" / "settings.json"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _decision(result) == "ask"


def test_guard_write_blocks_cursor_folder(tmp_path):
    target = tmp_path / ".cursor" / "foo"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_blocks_claude_skills_reflection(tmp_path):
    """.claude/skills/ holds auto-generated symlinks — writes must be refused,
    same as .cursor/ and .agents/. The agent has to edit mesh/ (or the owning
    layer) instead."""
    target = tmp_path / ".claude" / "skills" / "tiber--jira-workflow" / "SKILL.md"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_allows_claude_commands(tmp_path):
    """The block is scoped to .claude/skills/ — .claude/commands/ is committed
    content and stays writable."""
    target = tmp_path / ".claude" / "commands" / "custom.yaml"
    result = _run_hook(
        GUARD_WRITE,
        {"tool_input": {"file_path": str(target)}},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert not _is_block(result)


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
    assert "layer" in _reason(result).lower()


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


# --- FAIL-CLOSED test (#39) ---


def test_guard_bash_fails_closed_on_malformed_json():
    """Malformed/non-JSON stdin must deny (fail closed), never crash."""
    result = subprocess.run(
        [sys.executable, GUARD_BASH],
        input="THIS IS NOT JSON",
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ.copy(),
    )
    assert result.returncode == 0
    assert _is_block(result)


# ---------------------------------------------------------------------------
# guard_bash.py — TR-7 round 2: bare-root globs + per-segment compound eval
# ---------------------------------------------------------------------------

# --- Finding 1: bare-root glob/dotfile operands must be BLOCKED ---


@pytest.mark.parametrize("command", [
    "rm -rf /*",
    'rm -rf "/*"',
    "rm -rf /*.txt",
    "rm -rf /.*",
    "rm -rf /.bashrc",
    "rm -fr /*",
    "rm -rf -- /*",
])
def test_guard_bash_blocks_bare_root_glob(command):
    """rm -rf on the bare root + glob/dotfile (the lethal ``rm -rf /*`` family)
    must be blocked. Regression: dev blocked these; an earlier hardening pass
    let them through because the bare-root branch only matched ``/`` + subpath
    (a ``/`` followed by ``*`` neither started a subpath nor ended the operand).
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


# --- Finding 2: per-segment evaluation of compound commands (BLOCK) ---


@pytest.mark.parametrize("command", [
    "rm -rf dist && rm -rf /",
    "rm -rf node_modules && rm -rf /etc",
    "rm -rf /etc && rm -rf node_modules",
    "rm -rf build/ && rm -rf /home/user",
    "rm -rf /tmp/cache && rm -rf /usr",
    "rm -rf node_modules || rm -rf /",
    "rm -rf dist ; rm -rf /etc",
])
def test_guard_bash_blocks_compound_dangerous_segment(command):
    """A dangerous ``rm -rf`` in ANY segment of a compound command must block,
    even when another segment is a safe allowlisted cleanup. Regression: the
    safe-operand allowlist was matched against the whole command, so a safe
    ``rm -rf dist`` waived the block on ``rm -rf /`` in the same line.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


# --- Finding 2 negative: legitimate compound commands must still ALLOW ---


@pytest.mark.parametrize("command", [
    "cd app && rm -rf dist",
    "cd foo && rm -rf build",
    "rm -rf node_modules && rm -rf dist",
    "rm -rf dist && rm -rf build",
    "git rm -rf src && rm -rf node_modules",
])
def test_guard_bash_allows_compound_safe_segments(command):
    """Compound commands whose every rm -rf segment is safe/allowlisted (or
    whose rm is a subcommand like ``git rm``) must not be falsely blocked by
    per-segment evaluation.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert result.returncode == 0
    assert not _is_block(result), f"Unexpected block for: {command}"


# --- Finding 4: ${HOME} brace form must be BLOCKED like $HOME ---


@pytest.mark.parametrize("command", ["rm -rf $HOME", "rm -rf ${HOME}"])
def test_guard_bash_blocks_home_var(command):
    """Both ``$HOME`` and the brace form ``${HOME}`` must block."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


# --- Finding 3 / #39: unexpected exception fails CLOSED ---


def test_guard_bash_fails_closed_on_unexpected_exception():
    """If the matching logic raises an unexpected exception the hook must exit 0
    WITH a deny decision (#39: a crash used to wave the command through). We
    inject the failure by replacing _RM_RF_BLOCK with an object whose .search()
    raises, then run main() in a subprocess on a harmless payload.
    """
    hooks_dir = os.path.join(REPO_ROOT, "bin", "hooks")
    shim = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import guard_bash as g\n"
        "class Boom:\n"
        "    def search(self, *a, **k):\n"
        "        raise RuntimeError('injected failure')\n"
        "g._RM_RF_BLOCK = Boom()\n"
        "g.main()\n"
    ) % hooks_dir
    result = subprocess.run(
        [sys.executable, "-c", shim],
        input=json.dumps({"tool_input": {"command": "rm -rf node_modules"}}),
        capture_output=True,
        text=True,
        timeout=10,
        env=os.environ.copy(),
    )
    assert result.returncode == 0
    assert _is_block(result)
    assert "crashed" in _reason(result)


def test_guard_bash_redos_linear_on_pathological_input():
    """The rm -rf guard must stay linear: a long pathological operand must not
    trigger catastrophic backtracking (keeps the alternation prefix-anchored).
    """
    import time
    payload = "rm -rf /etc/" + "a" * 100000
    start = time.perf_counter()
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": payload}})
    elapsed = time.perf_counter() - start
    assert _is_block(result)
    # Generous bound (subprocess + interpreter startup dominate); a ReDoS would
    # blow far past this.
    assert elapsed < 5.0, f"rm -rf guard too slow ({elapsed:.2f}s) — possible ReDoS"


# ---------------------------------------------------------------------------
# guard_bash.py — TR-7 round 3
# F-1: multi-leading-slash root family must BLOCK (was an under-block)
# F-2: command-position anchoring (literal-string false positives -> ALLOW;
#      wrapped rm -rf still BLOCKs)
# ---------------------------------------------------------------------------

# --- F-1: a RUN of leading slashes resolves to the root and must BLOCK ---


@pytest.mark.parametrize("command", [
    "rm -rf //*",
    "rm -rf //",
    "rm -rf ///",
    "rm -rf //etc",
    "rm -rf //home/user",
    "rm -rf //.bashrc",
    'rm -rf "//*"',
    "rm -fr //",
    "rm -rf -- //etc",
    "rm -rf ////",
])
def test_guard_bash_blocks_multi_leading_slash_root(command):
    """A run of leading slashes is collapsed by the kernel (``//`` -> ``/``), so
    the multi-slash root family must block exactly like the single-slash forms.
    Regression (F-1): the bare-root branches only matched a SINGLE leading ``/``,
    so a second slash defeated both the glob lookahead and the whole-operand
    branch and these catastrophic commands were wrongly ALLOWED.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


@pytest.mark.parametrize("command", [
    "rm -rf /*",
    "rm -rf /etc/*",
    "rm -rf /home/*",
    "rm -rf /",
])
def test_guard_bash_single_slash_root_still_blocks(command):
    """F-1 must not regress the single-slash forms it generalises from."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


def test_guard_bash_allows_embedded_double_slash_relative():
    """``/+`` only collapses LEADING slashes; an embedded ``//`` in a relative
    operand must NOT be treated as a root operand (no false positive)."""
    for command in ("rm -rf foo//bar", "rm -rf ./a//b"):
        result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
        assert result.returncode == 0
        assert not _is_block(result), f"Unexpected block for: {command}"


# --- F-2: command-position anchoring ---
# Commands that merely CONTAIN the literal string ``rm -rf /...`` as a quoted
# argument to another command must be ALLOWED (their command is not ``rm``).


@pytest.mark.parametrize("command", [
    'git commit -m "...rm -rf /..."',
    'grep -r "rm -rf /" .',
    'grep -rn "rm -rf /etc" .',
    'echo "do not run rm -rf /etc"',
    'cat docs.md | grep "rm -rf /home"',
])
def test_guard_bash_allows_literal_rm_rf_in_argument(command):
    """F-2: ``rm -rf /...`` appearing inside a quoted argument to git/grep/echo/
    cat (etc.) must not be blocked — only a segment whose COMMAND is ``rm`` is
    dangerous. Regression: the block pattern used to ``search`` for the literal
    anywhere in the segment, so these harmless commands were wrongly BLOCKED.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert result.returncode == 0
    assert not _is_block(result), f"Unexpected block for: {command}"


# A wrapped ``rm -rf`` IS an rm invocation and must still BLOCK.


@pytest.mark.parametrize("command", [
    "sudo rm -rf /",
    "doas rm -rf /",
    "sudo rm -rf /etc",
    "doas rm -rf /home/user",
    "time rm -rf /",
    "nice rm -rf /",
    "nice -n 10 rm -rf /",
    "env FOO=bar rm -rf /",
    "env A=1 B=2 rm -rf /home",
    "sudo time rm -rf /",
    "sudo rm -rf //*",
])
def test_guard_bash_blocks_wrapped_rm_rf(command):
    """F-2: leading command wrappers (sudo/doas/time/nice/env VAR=val) are
    stripped before the command-position check, so a dangerous ``rm -rf`` behind
    them still blocks (no under-block relative to dev's ``sudo rm -rf /``)."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


@pytest.mark.parametrize("command", [
    "sudo rm -rf node_modules",
    "doas rm -rf dist",
    "env CI=1 rm -rf build",
    "nice -n 5 rm -rf /tmp/foo",
    "sudo ls /etc",
    "sudo cat /etc/passwd",
])
def test_guard_bash_wrapped_safe_or_nonrm_allows(command):
    """A wrapper in front of a SAFE rm operand (or a non-rm command) must still
    be allowed: wrapper-stripping must not introduce a false positive."""
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert result.returncode == 0
    assert not _is_block(result), f"Unexpected block for: {command}"


def test_guard_bash_known_gap_unlisted_wrapper():
    """Documented residual gap (honest framing): wrappers OUTSIDE the small
    listed set are not stripped, so ``stdbuf rm -rf /`` is not blocked. This is
    consistent with the variable-indirection / command-substitution gaps; real
    boundary is write-scope + human review. Asserted so the gap is explicit.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "stdbuf -oL rm -rf /"}}
    )
    assert not _is_block(result), (
        "Known gap: wrappers beyond the listed set are not stripped "
        "(best-effort limit)"
    )


def test_guard_bash_redos_linear_multi_slash_and_wrappers():
    """F-1/F-2 must stay linear: a long run of leading slashes and a long run of
    leading wrappers must not trigger catastrophic backtracking.
    """
    import time
    for payload in (
        "rm -rf " + "/" * 50000,            # long leading-slash run
        "sudo " * 20000 + "rm -rf /",       # long wrapper run
        "env " + " ".join(f"A{i}=v{i}" for i in range(10000)) + " rm -rf /",
    ):
        start = time.perf_counter()
        result = _run_hook(GUARD_BASH, {"tool_input": {"command": payload}})
        elapsed = time.perf_counter() - start
        assert _is_block(result), f"Expected block for pathological: {payload[:40]}..."
        assert elapsed < 5.0, (
            f"guard too slow ({elapsed:.2f}s) on pathological input — possible ReDoS"
        )


# ---------------------------------------------------------------------------
# guard_bash.py — TR-7 round 4
# Gap 1: full path to rm (``/bin/rm -rf /``) must BLOCK (was an under-block of
#        the command-position anchor, which required the token to be exactly rm).
# Gap 2: sudo/doas WITH FLAGS (``sudo -i rm -rf /``) must BLOCK (the wrapper
#        only consumed bare sudo/doas, leaving the option tokens in front of rm).
# ---------------------------------------------------------------------------


# --- Gap 1: optional ``/``-terminated path prefix before rm ---


@pytest.mark.parametrize("command", [
    "/bin/rm -rf /",
    "/usr/bin/rm -rf /",
    "/bin/rm -rf /etc",
    "/usr/bin/rm -fr /home",
    "./rm -rf /",
    "../bin/rm -rf /etc",
    "/bin/rm -rf -- /etc",
    "sudo /bin/rm -rf /",          # full-path rm behind a wrapper
])
def test_guard_bash_blocks_full_path_rm(command):
    """Gap 1: rm invoked by a full/relative path (prefix ending in ``/``) on a
    dangerous operand must block.  Regression: the command-position anchor
    required the token to be exactly ``rm``, so ``/bin/rm -rf /`` was ALLOWED.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


@pytest.mark.parametrize("command", [
    "git rm -rf src",              # the canonical must-never-block case
    "charm -rf foo",              # word ending in "rm", no slash -> not a path
    "myrm -rf /",                 # likewise
    "docker run --rm -rf-thing",  # flag, not a command path
    "/bin/rm -rf node_modules",   # full-path rm but SAFE operand
    "/bin/rm -rf /tmp/foo",       # full-path rm but /tmp/ operand is safe
])
def test_guard_bash_full_path_prefix_no_false_positive(command):
    """Gap 1 must NOT over-block: the prefix requires a trailing ``/`` so a word
    merely ending in ``rm`` (charm/myrm) or a flag (--rm) is never a path, and a
    safe operand stays allowed even when rm is invoked by full path.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert result.returncode == 0
    assert not _is_block(result), f"Unexpected block for: {command}"


# --- Gap 2: sudo/doas with flag-only options ---


@pytest.mark.parametrize("command", [
    "sudo -i rm -rf /",
    "sudo --preserve-env rm -rf /",
    "doas -n rm -rf /",
    "sudo -i -H rm -rf /",         # multiple flags
    "sudo --preserve-env rm -rf //*",
    "sudo rm -rf /",              # bare form must still block (no regression)
])
def test_guard_bash_blocks_flagged_sudo_doas(command):
    """Gap 2: option tokens between sudo/doas and rm are now consumed, so the
    dangerous ``rm -rf /`` behind them blocks.  Regression: only bare
    ``sudo``/``doas`` was stripped, so ``sudo -i rm -rf /`` was ALLOWED.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert _is_block(result), f"Expected block for: {command}"


@pytest.mark.parametrize("command", [
    "sudo -i ls",                 # flagged sudo, non-rm command
    "sudo -u postgres psql",      # value-flag + non-rm command
    "sudo --preserve-env make",   # flagged sudo, non-rm command
    "sudo rm -rf node_modules",   # flagged-wrapper path but SAFE operand
    "sudo apt-get install rm",    # rm is a package arg, not the command
])
def test_guard_bash_flagged_sudo_no_false_positive(command):
    """Gap 2 must NOT over-block: consuming flag tokens must not turn a non-rm
    command (or a safe rm operand) behind a flagged sudo into a block.
    """
    result = _run_hook(GUARD_BASH, {"tool_input": {"command": command}})
    assert result.returncode == 0
    assert not _is_block(result), f"Unexpected block for: {command}"


def test_guard_bash_known_gap_sudo_value_flag():
    """Documented residual gap (honest framing): a sudo/doas flag that takes a
    SEPARATE value argument (``-u root``) leaves a non-flag token (``root``) at
    command position, so ``sudo -u root rm -rf /`` is NOT blocked.  Consuming the
    value generically would wrongly swallow ``rm`` in value-less forms like
    ``sudo -i rm`` and under-block, so the value form is intentionally a gap.
    Asserted so the gap is explicit; real boundary is write-scope + human review.
    """
    result = _run_hook(
        GUARD_BASH, {"tool_input": {"command": "sudo -u root rm -rf /"}}
    )
    assert not _is_block(result), (
        "Known gap: sudo/doas value-taking flag (-u <user>) not consumed "
        "(best-effort limit)"
    )


def test_guard_bash_redos_linear_full_path_and_flagged_sudo():
    """Gap 1/Gap 2 must stay linear: a long ``/``-path prefix to rm, a long run
    of sudo flag tokens, and a long no-slash prefix must not backtrack.
    """
    import time
    for payload in (
        "/" + "a/" * 50000 + "rm -rf /",                # long path prefix
        "sudo " + "-x " * 50000 + "rm -rf /",           # long flag run
        "x" * 100000 + "rm -rf /",                      # long no-slash prefix (allow)
    ):
        start = time.perf_counter()
        result = _run_hook(GUARD_BASH, {"tool_input": {"command": payload}})
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, (
            f"guard too slow ({elapsed:.2f}s) on pathological input — possible ReDoS"
        )


# ---------------------------------------------------------------------------
# guard_write.py — shared policy core (_policy.decide)
# #39 fail closed, #40 layer bypass, #41 lexical aliases, #43 small fixes
# ---------------------------------------------------------------------------


def _write(path, ws, tool_name="Write", env=None, key="file_path"):
    run_env = {"MAICELIUM_ROOT": str(ws)}
    if env:
        run_env.update(env)
    return _run_hook(
        GUARD_WRITE,
        {"tool_name": tool_name, "tool_input": {key: str(path)}},
        env=run_env,
    )


def _symlink_dir(target, link):
    os.symlink(str(target), str(link), target_is_directory=True)


# --- #39: fail closed ---


@pytest.mark.parametrize("bad", ["\x00b", "\ud800b"])
def test_guard_write_denies_unrepresentable_path(tmp_path, bad):
    """A NUL byte or a lone surrogate used to crash the hook with exit 1
    (non-blocking) on POSIX; on Windows ntpath.realpath swallows the error and
    the path looked like a normal in-workspace file. Both are denied up front."""
    result = _write(str(tmp_path / "a") + bad, tmp_path)
    assert result.returncode == 0
    assert _is_block(result)


@pytest.mark.parametrize("stdin", ["", "THIS IS NOT JSON", "[1, 2]"])
def test_guard_write_fails_closed_on_invalid_input(tmp_path, stdin):
    result = subprocess.run(
        [sys.executable, GUARD_WRITE],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "MAICELIUM_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0
    assert _is_block(result)


@pytest.mark.parametrize(
    "tool_input",
    [{}, {"file_path": ""}, {"file_path": 42}, {"file_path": "relative/x.py"}],
)
def test_guard_write_denies_missing_or_relative_path(tmp_path, tool_input):
    result = _run_hook(
        GUARD_WRITE,
        {"tool_name": "Write", "tool_input": tool_input},
        env={"MAICELIUM_ROOT": str(tmp_path)},
    )
    assert _is_block(result)


def test_guard_write_fails_closed_on_unexpected_exception(tmp_path):
    """Any exception inside the policy is a deny, never a pass."""
    hooks_dir = os.path.join(REPO_ROOT, "bin", "hooks")
    shim = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import _policy\n"
        "def boom(*a, **k):\n"
        "    raise RuntimeError('injected failure')\n"
        "_policy.decide = boom\n"
        "import guard_write\n"
        "guard_write.main()\n"
    ) % hooks_dir
    result = subprocess.run(
        [sys.executable, "-c", shim],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "ok.md")}}),
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "MAICELIUM_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0
    assert _is_block(result)
    assert "crashed" in _reason(result)


def test_guard_write_allow_prints_nothing(tmp_path):
    """Allow must not emit permissionDecision "allow": that would skip
    Claude Code's own permission prompts."""
    result = _write(tmp_path / "notes" / "a.md", tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- #41: rules apply to the lexical AND the real identity ---


@requires_symlink
def test_guard_write_alias_symlink_to_settings_asks(tmp_path):
    """ln -s ../.claude/settings.json projects/notes.md, then Write notes.md."""
    ws = tmp_path / "ws"
    (ws / ".claude").mkdir(parents=True)
    (ws / ".claude" / "settings.json").write_text("{}\n")
    (ws / "projects").mkdir()
    alias = ws / "projects" / "notes.md"
    os.symlink(os.path.join("..", ".claude", "settings.json"), str(alias))
    assert _decision(_write(alias, ws)) == "ask"


@requires_symlink
def test_guard_write_alias_symlink_to_env_denied(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".env").write_text("K=v\n")
    alias = ws / "notes.txt"
    os.symlink(str(ws / ".env"), str(alias))
    assert _is_block(_write(alias, ws))


@requires_symlink
def test_guard_write_external_alias_to_workspace(tmp_path):
    """/tmp/w -> <ws>: the real identity keeps every workspace rule."""
    ws = tmp_path / "ws"
    (ws / ".claude").mkdir(parents=True)
    alias = tmp_path / "w"
    _symlink_dir(ws, alias)
    assert _decision(_write(alias / ".claude" / "settings.json", ws)) == "ask"
    assert _is_block(_write(alias / "WORKSPACE.md", ws))
    assert _is_block(_write(alias / ".cursor" / "rules" / "x.mdc", ws))
    assert _decision(_write(alias / "src" / "main.py", ws)) is None


@pytest.mark.parametrize(
    "rel,expected",
    [
        ((".CLAUDE", "settings.json"), "ask"),
        ((".Claude", "Settings.local.json"), "ask"),
        (("workspace.md",), "deny"),
        (("mAIcelium.CODE-WORKSPACE",), "deny"),
        ((".Claude", "Projects-Context.md"), "deny"),
        ((".ENV",), "deny"),
        (("sub", ".Env.Local"), "deny"),
        ((".Git", "config"), "deny"),
        (("Package-Lock.json",), "deny"),
        ((".CURSOR", "x"), "deny"),
        ((".Claude", "Skills", "x", "SKILL.md"), "deny"),
    ],
)
def test_guard_write_name_rules_ignore_case(tmp_path, rel, expected):
    """#43: case variants hit the same rule (they are the same file on
    macOS/Windows)."""
    assert _decision(_write(tmp_path.joinpath(*rel), tmp_path)) == expected


# --- #40: no layer-reflection bypass of the perimeter ---


@requires_symlink
def test_guard_write_malicious_layer_cannot_reach_home(tmp_path):
    """mesh/layers/evil -> ~ plus a reflection through it must not open ~."""
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    home.mkdir()
    (ws / "mesh" / "layers").mkdir(parents=True)
    (ws / "mesh" / "skills" / "_common").mkdir(parents=True)
    _symlink_dir(home, ws / "mesh" / "layers" / "evil")
    _symlink_dir(ws / "mesh" / "layers" / "evil", ws / "mesh" / "skills" / "_common" / "x")
    env = {"HOME": str(home), "USERPROFILE": str(home)}
    for target in (
        ws / "mesh" / "skills" / "_common" / "x" / ".bashrc",
        ws / "mesh" / "layers" / "evil" / ".bashrc",
    ):
        result = _write(target, ws, env=env)
        assert _is_block(result), target
        assert "outside" in _reason(result)


# --- #43: small fixes ---


@pytest.mark.parametrize("name", ["..notes.md", "a..b.md", "...md"])
def test_guard_write_allows_leading_dots_in_name(tmp_path, name):
    """Used to be refused by a startswith('..') check on the relative path."""
    assert _decision(_write(tmp_path / name, tmp_path)) is None


def test_guard_write_denies_git_pointer_file(tmp_path):
    """A .git FILE (worktree / submodule pointer) is protected like the dir."""
    result = _write(tmp_path / "sub" / ".git", tmp_path)
    assert _is_block(result)
    assert "git commit -F" in _reason(result)


@pytest.mark.parametrize(
    "name,expected",
    [
        (".env.example", None),
        (".env.prod.example", None),
        (".env.sample", None),
        (".env.template", None),
        (".env.production", "deny"),
        (".env", "deny"),
    ],
)
def test_guard_write_env_templates(tmp_path, name, expected):
    assert _decision(_write(tmp_path / name, tmp_path)) == expected


def test_guard_write_checks_notebook_edit(tmp_path):
    """NotebookEdit sends notebook_path, not file_path: it is checked too."""
    outside = tmp_path / "elsewhere" / "nb.ipynb"
    ws = tmp_path / "ws"
    ws.mkdir()
    assert _is_block(_write(outside, ws, tool_name="NotebookEdit", key="notebook_path"))
    inside = ws / "nb.ipynb"
    assert _decision(_write(inside, ws, tool_name="NotebookEdit", key="notebook_path")) is None


def test_guard_write_checks_multiedit(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    assert _is_block(_write(tmp_path / "elsewhere.py", ws, tool_name="MultiEdit"))


# --- Layer mounts are write roots (mesh/layers/<name> -> external repo) ---


def _layer_ws(tmp_path):
    """ws with mesh/skills/_common and mesh/layers, plus a fake $HOME."""
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    home.mkdir()
    (ws / "mesh" / "layers").mkdir(parents=True)
    (ws / "mesh" / "skills" / "_common").mkdir(parents=True)
    env = {"HOME": str(home), "USERPROFILE": str(home)}
    return ws, home, env


@requires_symlink
def test_guard_write_allows_external_layer_and_its_reflections(tmp_path):
    ws, home, env = _layer_ws(tmp_path)
    layer = tmp_path / "repos" / "core-layer"
    (layer / "skills" / "_common" / "foo").mkdir(parents=True)
    _symlink_dir(layer, ws / "mesh" / "layers" / "core")
    _symlink_dir(
        ws / "mesh" / "layers" / "core" / "skills" / "_common" / "foo",
        ws / "mesh" / "skills" / "_common" / "foo",
    )
    for target in (
        ws / "mesh" / "skills" / "_common" / "foo" / "SKILL.md",  # reflection
        ws / "mesh" / "skills" / "_common" / "foo" / "new.md",  # new file via it
        ws / "mesh" / "layers" / "core" / "skills" / "_common" / "foo" / "SKILL.md",
        layer / "README.md",  # the layer repo by its real path
    ):
        assert _decision(_write(target, ws, env=env)) is None, target
    # Name rules still apply inside a layer.
    assert _is_block(_write(layer / ".env", ws, env=env))
    assert _is_block(_write(layer / ".git" / "config", ws, env=env))


@requires_symlink
@pytest.mark.parametrize("kind", ["home", "hidden-home", "claude-dir", "ws-ancestor"])
def test_guard_write_rejects_dangerous_layer_targets(tmp_path, kind):
    """A layer symlink to $HOME, a hidden home folder, ~/.claude or a folder
    containing the workspace never becomes a write root."""
    ws, home, env = _layer_ws(tmp_path)
    target_dir = {
        "home": home,
        "hidden-home": home / ".aws",
        "claude-dir": home / ".claude",
        "ws-ancestor": tmp_path,
    }[kind]
    target_dir.mkdir(parents=True, exist_ok=True)
    _symlink_dir(target_dir, ws / "mesh" / "layers" / "evil")
    victim = ws / "mesh" / "layers" / "evil" / "victim.txt"
    result = _write(victim, ws, env=env)
    if kind == "ws-ancestor":
        # The path itself is inside the workspace through the symlink, but its
        # real location is <tmp>/victim.txt, which is not.
        assert os.path.realpath(victim) == os.path.realpath(tmp_path / "victim.txt")
    assert _is_block(result), kind
    assert "outside" in _reason(result)


@requires_symlink
def test_guard_write_ignores_layers_when_mesh_layers_is_a_symlink(tmp_path):
    """mesh/layers must be a real directory; if it is a symlink nothing under
    it is trusted as a mount."""
    ws, home, env = _layer_ws(tmp_path)
    (ws / "mesh" / "layers").rmdir()
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "repo").mkdir(parents=True)
    _symlink_dir(elsewhere, ws / "mesh" / "layers")
    assert _is_block(_write(elsewhere / "repo" / "a.md", ws, env=env))
