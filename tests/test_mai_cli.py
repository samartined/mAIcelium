"""Tests for maicelium_cli.py — the `mai` CLI router.

All 34 test intentions from the canonical spec:
  UNIT-1..10, INT-1..15, PK-1..6, SH-1, CI-1..2

Import rules:
- maicelium_cli is NEVER imported at module top-level; always inside test
  functions or fixtures (lazy import), so pytest --collect-only exits 0
  even when maicelium_cli.py does not yet exist.
- `from _marks import requires_symlink` is fine at module level (conftest
  already puts tests/ on sys.path before collection).
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import tomllib

from _marks import requires_symlink

# ---------------------------------------------------------------------------
# Repo-level constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
MAICELIUM_CLI_PY = REPO_ROOT / "maicelium_cli.py"
TESTS_DIR = REPO_ROOT / "tests"


# ---------------------------------------------------------------------------
# Helper: build a minimal fake workspace (bin/_bootstrap.py + mesh/ marker)
# ---------------------------------------------------------------------------
def _make_fake_ws(tmp_path, name="ws"):
    """Return a tmp dir that looks like a mAIcelium workspace.

    Contains:  bin/_bootstrap.py   mesh/   projects/
    This is the marker pair used by the cwd-walk in root resolution.
    """
    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "bin").mkdir(exist_ok=True)
    (ws / "bin" / "_bootstrap.py").write_text("# stub\n", encoding="utf-8")
    (ws / "mesh").mkdir(exist_ok=True)
    (ws / "projects").mkdir(exist_ok=True)
    return ws


def _cli_env(root, *, encoding="utf-8", extra=None):
    """Return a clean env dict for subprocess CLI tests."""
    env = os.environ.copy()
    env["MAICELIUM_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = encoding
    if extra:
        env.update(extra)
    return env


def _run_cli(*args, root, encoding="utf-8", extra_env=None, cwd=None, timeout=20):
    """Run maicelium_cli.py as a subprocess and return CompletedProcess."""
    env = _cli_env(root, encoding=encoding, extra=extra_env or {})
    return subprocess.run(
        [sys.executable, str(MAICELIUM_CLI_PY), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        cwd=cwd,
    )


# ===========================================================================
# UNIT TESTS — monkeypatched / pure-import (no real subprocess spawn)
# ===========================================================================


class TestUNIT1:
    """UNIT-1: VERBS registry points only at real, existing scripts."""

    def test_verbs_registry_all_canonical_verbs_present(self, monkeypatch):
        """UNIT-1: All 12 canonical verbs present and scripts exist on disk."""
        import importlib, sys as _sys
        # Lazy import — maicelium_cli.py may not exist yet
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli  # noqa: E402

        expected_verbs = {
            "init", "add", "remove", "sync", "separate-git",
            "add-mcp", "remove-mcp", "add-layer", "remove-layer",
            "set-flag", "list", "health",
        }
        assert set(maicelium_cli.VERBS.keys()) == expected_verbs, (
            f"VERBS keys: {set(maicelium_cli.VERBS.keys())}"
        )

    def test_each_verb_script_exists(self):
        """UNIT-1: Each rel_path in VERBS resolves to an existing file under repo root."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        root = REPO_ROOT
        for verb, spec in maicelium_cli.VERBS.items():
            path = root / spec["rel_path"]
            assert path.is_file(), (
                f"Verb '{verb}' -> rel_path '{spec['rel_path']}' not found at {path}"
            )

    def test_bin_verbs_under_bin(self):
        """UNIT-1: 10 bin verbs map to files under bin/; list+health under mesh/."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        bin_verbs = {
            "init", "add", "remove", "sync", "separate-git",
            "add-mcp", "remove-mcp", "add-layer", "remove-layer", "set-flag",
        }
        mesh_verbs = {"list", "health"}

        for verb in bin_verbs:
            rel = maicelium_cli.VERBS[verb]["rel_path"]
            assert rel.startswith("bin/"), (
                f"Verb '{verb}' should be under bin/, got: {rel}"
            )
        for verb in mesh_verbs:
            rel = maicelium_cli.VERBS[verb]["rel_path"]
            assert rel.startswith("mesh/"), (
                f"Verb '{verb}' should be under mesh/, got: {rel}"
            )

    def test_add_remove_target_exact_bin_scripts(self):
        """UNIT-1: add -> bin/add_project.py, remove -> bin/remove_project.py (EXACT-name)."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        assert maicelium_cli.VERBS["add"]["rel_path"] == "bin/add_project.py"
        assert maicelium_cli.VERBS["remove"]["rel_path"] == "bin/remove_project.py"


class TestUNIT2:
    """UNIT-2: ALIASES resolve to canonical verbs, hyphen==underscore, no collisions."""

    def _get_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_add_aliases(self):
        """UNIT-2: add-project and add_project resolve to 'add'."""
        cli = self._get_cli()
        assert cli.ALIASES.get("add-project") == "add"
        assert cli.ALIASES.get("add_project") == "add"

    def test_remove_aliases(self):
        """UNIT-2: rm, remove-project, remove_project resolve to 'remove'."""
        cli = self._get_cli()
        assert cli.ALIASES.get("rm") == "remove"
        assert cli.ALIASES.get("remove-project") == "remove"
        assert cli.ALIASES.get("remove_project") == "remove"

    def test_list_aliases(self):
        """UNIT-2: ls, list-projects, list_projects resolve to 'list'."""
        cli = self._get_cli()
        assert cli.ALIASES.get("ls") == "list"
        assert cli.ALIASES.get("list-projects") == "list"
        assert cli.ALIASES.get("list_projects") == "list"

    def test_health_aliases(self):
        """UNIT-2: project-health resolves to 'health'."""
        cli = self._get_cli()
        assert cli.ALIASES.get("project-health") == "health"

    def test_hyphen_underscore_equivalence(self):
        """UNIT-2: Hyphen and underscore aliases resolve identically."""
        cli = self._get_cli()
        # For any alias pair that differs only in - vs _, both must resolve the same
        pairs = [
            ("add-project", "add_project"),
            ("remove-project", "remove_project"),
            ("list-projects", "list_projects"),
        ]
        for hyph, under in pairs:
            assert cli.ALIASES.get(hyph) == cli.ALIASES.get(under), (
                f"'{hyph}' -> {cli.ALIASES.get(hyph)} != '{under}' -> {cli.ALIASES.get(under)}"
            )

    def test_no_alias_collision(self):
        """UNIT-2: No alias maps to two different canonical verbs."""
        cli = self._get_cli()
        # All values must be valid canonical verbs
        for alias, canonical in cli.ALIASES.items():
            assert canonical in cli.VERBS, (
                f"Alias '{alias}' maps to '{canonical}' which is not a canonical verb"
            )

    def test_rm_and_ls_target_equals_canonical(self):
        """UNIT-2: Alias target script matches the canonical verb's target."""
        cli = self._get_cli()
        rm_canonical = cli.ALIASES.get("rm")
        ls_canonical = cli.ALIASES.get("ls")
        assert cli.VERBS["remove"]["rel_path"] == cli.VERBS[rm_canonical]["rel_path"]
        assert cli.VERBS["list"]["rel_path"] == cli.VERBS[ls_canonical]["rel_path"]


class TestUNIT3:
    """UNIT-3: main() consumes mai-level flags before the verb and forwards the rest verbatim."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_sync_check_only_forwarded(self, monkeypatch, tmp_path):
        """UNIT-3: main(['sync','--check-only','--dry-run']) forwards args to dispatch."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_dispatch(verb, args, root):
            captured["verb"] = verb
            captured["args"] = list(args)
            return 0

        monkeypatch.setattr(cli, "dispatch", fake_dispatch)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        cli.main(["sync", "--check-only", "--dry-run"])

        assert captured["verb"] == "sync"
        assert "--check-only" in captured["args"]
        assert "--dry-run" in captured["args"]

    def test_root_consumed_not_forwarded(self, monkeypatch, tmp_path):
        """UNIT-3: --root <dir> is consumed by router and NOT forwarded to dispatch."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_dispatch(verb, args, root):
            captured["verb"] = verb
            captured["args"] = list(args)
            captured["root"] = root
            return 0

        monkeypatch.setattr(cli, "dispatch", fake_dispatch)
        cli.main(["--root", str(ws), "add", "foo", "/bar"])

        assert captured["verb"] == "add"
        assert "foo" in captured["args"]
        assert "/bar" in captured["args"]
        assert "--root" not in captured["args"]
        assert str(ws) not in captured["args"]

    def test_sync_help_forwarded(self, monkeypatch, tmp_path):
        """UNIT-3: main(['sync','--help']) forwards --help to child (not consumed by router)."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_dispatch(verb, args, root):
            captured["verb"] = verb
            captured["args"] = list(args)
            return 0

        monkeypatch.setattr(cli, "dispatch", fake_dispatch)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        cli.main(["sync", "--help"])

        assert captured["verb"] == "sync"
        assert "--help" in captured["args"]

    def test_unknown_verb_flags_not_rejected(self, monkeypatch, tmp_path):
        """UNIT-3: Verb-level unknown flags are NOT rejected by the router."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_dispatch(verb, args, root):
            captured["verb"] = verb
            captured["args"] = list(args)
            return 0

        monkeypatch.setattr(cli, "dispatch", fake_dispatch)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        result = cli.main(["sync", "--totally-unknown-flag"])

        # Router should NOT have returned 2 (unknown verb) — it dispatched
        assert "verb" in captured, "Router should have dispatched, not errored on unknown flag"
        assert "--totally-unknown-flag" in captured["args"]

    def test_unknown_global_flag_no_verb_errors_2(self, monkeypatch, tmp_path):
        """UNIT-3 (adversarial gap): an unknown GLOBAL flag with no verb is a usage
        error (exit 2), not a silent help/exit-0. `mai --foo` previously fell through
        to help and swallowed the option."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        dispatched = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatched.append(a) or 0)
        result = cli.main(["--totally-unknown-global"])
        assert result == 2
        assert not dispatched

    def test_unknown_global_flag_before_verb_errors_2(self, monkeypatch, tmp_path):
        """UNIT-3 (adversarial gap): an unknown GLOBAL flag before a valid verb must
        error (exit 2), not be silently dropped while the verb still dispatches."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        dispatched = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatched.append(a) or 0)
        result = cli.main(["--totally-unknown-global", "list"])
        assert result == 2
        assert not dispatched, "unknown global flag must not be silently dropped"


class TestUNIT4:
    """UNIT-4: --version/-V prints the version and exits 0 without dispatching."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_version_flag_exits_0(self, monkeypatch, tmp_path, capsys):
        """UNIT-4: main(['--version']) returns 0."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))

        dispatch_called = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatch_called.append(a) or 0)

        rc = cli.main(["--version"])
        assert rc == 0
        assert not dispatch_called, "dispatch must NOT be called for --version"

    def test_version_output_contains_version(self, monkeypatch, tmp_path, capsys):
        """UNIT-4: --version output contains the version string."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["--version"])
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert cli.__version__ in combined or any(
            c.isdigit() for c in combined
        ), f"No version in output: {combined!r}"

    def test_version_output_mentions_mai_or_maicelium(self, monkeypatch, tmp_path, capsys):
        """UNIT-4: --version output mentions 'mai' or 'maicelium'."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["--version"])
        captured = capsys.readouterr()
        combined = (captured.out + captured.err).lower()
        assert "mai" in combined or "maicelium" in combined

    def test_capital_V_flag(self, monkeypatch, tmp_path, capsys):
        """UNIT-4: -V also prints version and exits 0."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        dispatch_called = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatch_called.append(a) or 0)

        rc = cli.main(["-V"])
        assert rc == 0
        assert not dispatch_called


class TestUNIT5:
    """UNIT-5: bare `mai` and `mai --help`/-h list all verbs, exit 0."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_bare_mai_exits_0(self, monkeypatch, tmp_path, capsys):
        """UNIT-5: main([]) returns 0. Challenges prior prototype's sys.exit(1)."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        dispatch_called = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatch_called.append(a) or 0)

        rc = cli.main([])
        assert rc == 0
        assert not dispatch_called

    def test_help_flag_exits_0(self, monkeypatch, tmp_path, capsys):
        """UNIT-5: main(['--help']) returns 0."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        rc = cli.main(["--help"])
        assert rc == 0

    def test_help_lists_all_verbs(self, monkeypatch, tmp_path, capsys):
        """UNIT-5: Help output lists all 12 canonical verbs."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["--help"])
        captured = capsys.readouterr()
        out = captured.out + captured.err

        expected_verbs = [
            "init", "add", "remove", "sync", "separate-git",
            "add-mcp", "remove-mcp", "add-layer", "remove-layer",
            "set-flag", "list", "health",
        ]
        for verb in expected_verbs:
            assert verb in out, f"Expected verb '{verb}' in help output"

    def test_help_mentions_root_and_version(self, monkeypatch, tmp_path, capsys):
        """UNIT-5: Help output mentions --root and --version."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["--help"])
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "--root" in out
        assert "--version" in out


class TestUNIT6:
    """UNIT-6: unknown verb errors with exit 2 and a helpful message."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_unknown_verb_returns_2(self, monkeypatch, tmp_path, capsys):
        """UNIT-6: main(['frobnicate']) returns 2 (router-usage error)."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        dispatch_called = []
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: dispatch_called.append(a) or 0)

        rc = cli.main(["frobnicate"])
        assert rc == 2
        assert not dispatch_called

    def test_unknown_verb_message_names_verb(self, monkeypatch, tmp_path, capsys):
        """UNIT-6: Error message names the unknown verb."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["frobnicate"])
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "frobnicate" in combined

    def test_unknown_verb_message_points_to_help(self, monkeypatch, tmp_path, capsys):
        """UNIT-6: Error message references --help or lists valid verbs."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        cli.main(["frobnicate"])
        captured = capsys.readouterr()
        combined = (captured.out + captured.err).lower()
        assert "--help" in combined or "help" in combined


class TestUNIT7:
    """UNIT-7: resolve_root_for_cli precedence --root > MAICELIUM_ROOT > cwd-walk > __file__."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_root_flag_wins_over_env(self, tmp_path):
        """UNIT-7: --root wins even when MAICELIUM_ROOT is also set."""
        cli = self._import_cli()
        ws1 = _make_fake_ws(tmp_path, "ws1")
        ws2 = _make_fake_ws(tmp_path, "ws2")

        result = cli.resolve_root_for_cli(
            args=["--root", str(ws1), "list"],
            env={"MAICELIUM_ROOT": str(ws2)},
            cwd=str(tmp_path),
            file=str(MAICELIUM_CLI_PY),
        )
        assert result == str(ws1), f"Expected ws1, got {result}"

    def test_env_wins_over_cwd_walk(self, tmp_path):
        """UNIT-7: MAICELIUM_ROOT wins over a walkable cwd."""
        cli = self._import_cli()
        ws_env = _make_fake_ws(tmp_path, "ws_env")
        ws_cwd = _make_fake_ws(tmp_path, "ws_cwd")
        subdir = ws_cwd / "projects" / "foo"
        subdir.mkdir(parents=True)

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={"MAICELIUM_ROOT": str(ws_env)},
            cwd=str(subdir),
            file=str(MAICELIUM_CLI_PY),
        )
        assert result == str(ws_env), f"Expected ws_env, got {result}"

    def test_cwd_walk_finds_workspace_marker(self, tmp_path):
        """UNIT-7: A cwd nested under bin/_bootstrap.py+mesh/ resolves to that dir."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path, "ws")
        subdir = ws / "projects" / "foo" / "bar"
        subdir.mkdir(parents=True)

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={},
            cwd=str(subdir),
            file=str(tmp_path / "elsewhere" / "maicelium_cli.py"),
        )
        assert result == str(ws), f"Expected ws via cwd-walk, got {result}"

    def test_file_fallback_when_no_marker(self, tmp_path):
        """UNIT-7: No marker in the cwd tree falls back to the maicelium_cli.py dir.

        The __file__ fallback dir must itself be a real workspace (the editable-install
        layout: maicelium_cli.py sits next to bin/_bootstrap.py + mesh/). If it is NOT a
        workspace, that is the 'no resolvable root' case (covered by INT-14)."""
        cli = self._import_cli()
        # The install dir IS a workspace; cwd has no marker, so layer 4 is used.
        fake_cli_dir = _make_fake_ws(tmp_path, "install_dir")
        fake_cli = fake_cli_dir / "maicelium_cli.py"
        fake_cli.write_text("# stub\n", encoding="utf-8")

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={},
            cwd=str(tmp_path / "some" / "other" / "dir"),
            file=str(fake_cli),
        )
        assert result == str(fake_cli_dir), f"Expected __file__ dir fallback, got {result}"

    def test_nonexistent_root_raises_exit_2(self, tmp_path, capsys):
        """UNIT-7: A non-existent --root path causes a usage error (returns/raises exit 2)."""
        cli = self._import_cli()
        nonexistent = str(tmp_path / "does_not_exist")

        try:
            result = cli.resolve_root_for_cli(
                args=["--root", nonexistent, "list"],
                env={},
                cwd=str(tmp_path),
                file=str(MAICELIUM_CLI_PY),
            )
            # If it doesn't raise, it should be an error indicator
            # (some implementations might return None or signal differently)
            pytest.fail(f"Expected exit 2 for non-existent --root, got result={result!r}")
        except SystemExit as e:
            assert e.code == 2, f"Expected exit code 2, got {e.code}"
        except (ValueError, FileNotFoundError):
            pass  # Acceptable signal for non-existent path


class TestUNIT8:
    """UNIT-8: dispatch builds the correct subprocess argv, cwd, env (no real spawn)."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_dispatch_correct_argv(self, monkeypatch, tmp_path):
        """UNIT-8: argv == [sys.executable, str(ROOT/bin/add_project.py), 'foo', '/bar']."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

            class FakeResult:
                returncode = 0
            return FakeResult()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        cli.dispatch("add", ["foo", "/bar"], str(ws))

        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][1].endswith(os.path.join("bin", "add_project.py"))
        assert "foo" in captured["cmd"]
        assert "/bar" in captured["cmd"]

    def test_dispatch_cwd_is_root(self, monkeypatch, tmp_path):
        """UNIT-8: cwd in subprocess.run is the resolved ROOT."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["kwargs"] = kwargs

            class FakeResult:
                returncode = 0
            return FakeResult()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        cli.dispatch("add", ["foo", "/bar"], str(ws))

        assert captured["kwargs"].get("cwd") == str(ws)

    def test_dispatch_env_contains_maicelium_root(self, monkeypatch, tmp_path):
        """UNIT-8: MAICELIUM_ROOT is exported to child env."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["kwargs"] = kwargs

            class FakeResult:
                returncode = 0
            return FakeResult()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        cli.dispatch("add", ["foo", "/bar"], str(ws))

        env = captured["kwargs"].get("env", {})
        assert env.get("MAICELIUM_ROOT") == str(ws)

    def test_dispatch_check_is_false(self, monkeypatch, tmp_path):
        """UNIT-8: check=False so router owns returncode handling."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["kwargs"] = kwargs

            class FakeResult:
                returncode = 0
            return FakeResult()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        cli.dispatch("add", ["foo"], str(ws))

        assert captured["kwargs"].get("check") is False

    def test_dispatch_propagates_returncode(self, monkeypatch, tmp_path):
        """UNIT-8: dispatch returns the faked returncode unchanged (0,1,2,7)."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)

        for expected_rc in [0, 1, 2, 7]:
            def fake_run(cmd, _rc=expected_rc, **kwargs):
                class FakeResult:
                    returncode = _rc
                return FakeResult()

            monkeypatch.setattr(cli.subprocess, "run", fake_run)
            rc = cli.dispatch("add", ["foo"], str(ws))
            assert rc == expected_rc, f"Expected rc={expected_rc}, got {rc}"


class TestUNIT9:
    """UNIT-9: cwd-walk false-positive: nearest-ancestor marker wins on multi-workspace tree."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_nested_inner_wins_over_outer(self, tmp_path):
        """UNIT-9: Nested inner+outer markers — cwd inside inner resolves to inner, not outer."""
        cli = self._import_cli()
        outer = _make_fake_ws(tmp_path, "outer")
        inner = _make_fake_ws(outer, "inner")
        cwd_inside_inner = inner / "projects"
        cwd_inside_inner.mkdir(exist_ok=True)

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={},
            cwd=str(cwd_inside_inner),
            file=str(tmp_path / "elsewhere" / "maicelium_cli.py"),
        )
        assert result == str(inner), (
            f"First-match-wins should pick inner={inner}, got {result}"
        )
        assert result != str(outer), "Should NOT have picked the outer workspace"

    def test_sibling_workspace_not_selected(self, tmp_path):
        """UNIT-9: A sibling marker dir NOT on the cwd ancestor chain is never selected."""
        cli = self._import_cli()
        ws_a = _make_fake_ws(tmp_path, "ws_a")
        ws_b = _make_fake_ws(tmp_path, "ws_b")  # noqa: F841  sibling
        subdir = ws_a / "projects" / "myrepo"
        subdir.mkdir(parents=True)

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={},
            cwd=str(subdir),
            file=str(tmp_path / "elsewhere" / "maicelium_cli.py"),
        )
        assert result == str(ws_a), (
            f"Should have resolved ws_a, got {result}"
        )


class TestUNIT10:
    """UNIT-10: MAICELIUM_ROOT env is passed through verbatim (documented asymmetric trust)."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_env_root_trusted_without_existence_check(self, tmp_path):
        """UNIT-10: MAICELIUM_ROOT set to non-existent dir is returned as-is (no validation).

        VERIFIED: platform.resolve_root() line 20 returns env value with NO existence check,
        asymmetric vs --root which IS existence-validated. Pinned per doubt #4.
        """
        cli = self._import_cli()
        nonexistent = str(tmp_path / "does_not_exist_at_all")

        result = cli.resolve_root_for_cli(
            args=["list"],
            env={"MAICELIUM_ROOT": nonexistent},
            cwd=str(tmp_path),
            file=str(MAICELIUM_CLI_PY),
        )
        # The env value is passed through verbatim — no existence validation
        assert result == nonexistent, (
            f"Expected env root passed through verbatim, got {result!r}. "
            "Note: --root IS validated but MAICELIUM_ROOT is NOT (asymmetric, doubt #4)."
        )

    def test_child_env_maicelium_root_equals_unvalidated_env(self, monkeypatch, tmp_path):
        """UNIT-10: Child env MAICELIUM_ROOT equals the (unvalidated) env value."""
        cli = self._import_cli()
        nonexistent = str(tmp_path / "does_not_exist")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env", {})

            class FakeResult:
                returncode = 0
            return FakeResult()

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        monkeypatch.setenv("MAICELIUM_ROOT", nonexistent)
        cli.main(["list"])

        assert captured.get("env", {}).get("MAICELIUM_ROOT") == nonexistent

    def test_nonexistent_root_flag_rejected(self, tmp_path, capsys):
        """UNIT-10: A non-existent --root IS rejected with exit 2 (asymmetry documented).

        Contrast: MAICELIUM_ROOT env is not validated (UNIT-10 above).
        Ref: doubt #4 — whether to also validate env.
        """
        cli = self._import_cli()
        nonexistent = str(tmp_path / "does_not_exist")

        try:
            result = cli.resolve_root_for_cli(
                args=["--root", nonexistent, "list"],
                env={},
                cwd=str(tmp_path),
                file=str(MAICELIUM_CLI_PY),
            )
            pytest.fail(f"Expected exit 2 for non-existent --root, got {result!r}")
        except SystemExit as e:
            assert e.code == 2
        except (ValueError, FileNotFoundError):
            pass


# ===========================================================================
# INTEGRATION TESTS — real subprocess invocations of maicelium_cli.py
# ===========================================================================


class TestINT1:
    """INT-1: mai --version end-to-end via subprocess."""

    def test_version_returncode_0(self, tmp_path):
        """INT-1: returncode == 0."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("--version", root=ws)
        assert result.returncode == 0, (
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_version_stdout_contains_version(self, tmp_path):
        """INT-1: stdout contains the version."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("--version", root=ws)
        combined = result.stdout + result.stderr
        assert any(c.isdigit() for c in combined), (
            f"No version digits in output: {combined!r}"
        )

    def test_version_no_traceback(self, tmp_path):
        """INT-1: stderr contains no 'Traceback'."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("--version", root=ws)
        assert "Traceback" not in result.stderr


class TestINT2:
    """INT-2: mai list routes to list_projects on an empty workspace."""

    def test_list_empty_workspace_returncode_0(self, tmp_path):
        """INT-2: returncode == 0."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("list", root=ws)
        assert result.returncode == 0, (
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_list_empty_workspace_message(self, tmp_path):
        """INT-2: stdout contains 'No projects directory found' or 'No projects are currently linked'."""
        ws = _make_fake_ws(tmp_path)
        # Remove the projects/ dir to trigger 'No projects directory found'
        import shutil
        shutil.rmtree(ws / "projects")
        result = _run_cli("list", root=ws)
        assert "No projects directory found" in result.stdout or \
               "No projects" in result.stdout, (
            f"Expected no-projects message, got: {result.stdout!r}"
        )

    def test_list_same_as_direct_script(self, tmp_path):
        """INT-2: Behaves identically to invoking list_projects.py directly."""
        ws = _make_fake_ws(tmp_path)
        import shutil
        shutil.rmtree(ws / "projects")

        script_path = REPO_ROOT / "mesh" / "commands" / "scripts" / "list_projects.py"
        env = _cli_env(ws)

        direct_result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=20,
        )
        cli_result = _run_cli("list", root=ws)

        assert cli_result.returncode == direct_result.returncode
        # Both should contain the same no-projects signal
        assert "No projects" in cli_result.stdout or "No projects" in direct_result.stdout


class TestINT3:
    """INT-3: mai remove with no args passes through the child's exit 1 (not router-2)."""

    def test_remove_no_args_returncode_1(self, tmp_path):
        """INT-3: returncode == 1 (child's), NOT 2 (router's)."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("remove", root=ws)
        assert result.returncode == 1, (
            f"Expected exit 1 from child (not router-2). "
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_remove_no_args_shows_usage(self, tmp_path):
        """INT-3: stdout contains 'Usage' and 'remove_project'."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("remove", root=ws)
        assert "Usage" in result.stdout or "usage" in result.stdout.lower(), (
            f"Expected 'Usage' in stdout: {result.stdout!r}"
        )

    def test_remove_no_args_not_router_error(self, tmp_path):
        """INT-3: Router did NOT convert it to exit 2."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("remove", root=ws)
        # If it were a router error it would return 2; child returns 1
        assert result.returncode != 2, "Router should NOT convert child-1 to router-2"


class TestINT4:
    """INT-4: mai sync --check-only forwards the flag and returns the child's code."""

    def test_sync_check_only_no_unrecognized_args(self, tmp_path):
        """INT-4: stderr does NOT contain 'unrecognized arguments'."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--check-only", root=ws)
        assert "unrecognized arguments" not in result.stderr, (
            f"Got 'unrecognized arguments' in stderr: {result.stderr!r}"
        )

    def test_sync_check_only_returncode_0_or_1(self, tmp_path):
        """INT-4: returncode is 0 or 1 (real --check-only sync result) or 2 (no symlink)."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--check-only", root=ws)
        # 0 = no drift, 1 = drift found, 2 = no symlink privilege
        assert result.returncode in (0, 1, 2), (
            f"Unexpected returncode {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


class TestINT5:
    """INT-5: mai sync --help forwards --help to the child (script's own help, exit 0)."""

    def test_sync_help_returncode_0(self, tmp_path):
        """INT-5: returncode == 0."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--help", root=ws)
        assert result.returncode == 0, (
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_sync_help_shows_child_flags(self, tmp_path):
        """INT-5: stdout contains '--check-only' and '--fix-drift' (child's own help)."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--help", root=ws)
        assert "--check-only" in result.stdout, (
            f"Expected '--check-only' in stdout: {result.stdout!r}"
        )
        assert "--fix-drift" in result.stdout, (
            f"Expected '--fix-drift' in stdout: {result.stdout!r}"
        )

    def test_sync_help_not_mai_level_help(self, tmp_path):
        """INT-5: Output is the child's help, NOT the mai router's verb list."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--help", root=ws)
        # The router's help would list verbs like 'init', 'add', 'remove', etc.
        # The child's help should NOT contain that top-level verb enumeration
        # (It's fine if 'sync' appears as the script name, but not as a verb list)
        # The definitive test: child help contains check-only (above)
        # and does NOT contain the mai-level verb list overview
        assert "init" not in result.stdout or "--check-only" in result.stdout, (
            "Output looks like mai-level help rather than sync's own help"
        )


class TestINT6:
    """INT-6: mai unknown verb exits 2 end-to-end."""

    def test_unknown_verb_returncode_2(self, tmp_path):
        """INT-6: returncode == 2."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("frobnicate", root=ws)
        assert result.returncode == 2, (
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_unknown_verb_names_verb(self, tmp_path):
        """INT-6: stderr or stdout contains 'frobnicate'."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("frobnicate", root=ws)
        combined = result.stdout + result.stderr
        assert "frobnicate" in combined, f"Expected 'frobnicate' in output: {combined!r}"

    def test_unknown_verb_references_help(self, tmp_path):
        """INT-6: Message references help."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("frobnicate", root=ws)
        combined = (result.stdout + result.stderr).lower()
        assert "help" in combined, f"Expected 'help' reference in output: {combined!r}"


class TestINT7:
    """INT-7: mai resolves root via upward cwd-walk from a subdir with no env."""

    def test_cwd_walk_from_subdir(self):
        """INT-7: Works when launched at least one directory below the root; no MAICELIUM_ROOT env."""
        # Use the REAL repo as the workspace (it has bin/_bootstrap.py + mesh/)
        subdir = REPO_ROOT / "tests"
        env = os.environ.copy()
        env.pop("MAICELIUM_ROOT", None)
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, cwd=str(subdir), timeout=20,
        )
        assert result.returncode == 0, (
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


class TestINT8:
    """INT-8: mai add routes to the EXACT-name bin script, not the fuzzy mesh variant."""

    def test_add_verbs_target_bin_script(self):
        """INT-8: VERBS['add'] target ends with bin/add_project.py (not mesh variant)."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        rel = maicelium_cli.VERBS["add"]["rel_path"]
        assert rel == "bin/add_project.py", (
            f"Expected bin/add_project.py, got {rel!r}. "
            "The CLI must NOT use the fuzzy mesh/commands/scripts/add_project.py variant."
        )

    def test_add_no_args_no_fuzzy_prompt(self, tmp_path):
        """INT-8: No-arg add shows bin/add_project.py behavior (Usage), not fuzzy 'did you mean'."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("add", root=ws)
        combined = result.stdout + result.stderr
        # Fuzzy mesh variant would show 'did you mean' or 'fuzzy'; bin variant shows Usage
        assert "did you mean" not in combined.lower(), (
            "Got fuzzy-match output — CLI is routing to mesh variant, not bin/add_project.py"
        )

    def test_add_no_args_returncode_matches_bin_script(self, tmp_path):
        """INT-8: No-arg add exit code matches bin/add_project.py's no-arg behavior."""
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("add", root=ws)
        # bin/add_project.py no-arg exits 1 (Usage error)
        assert result.returncode == 1, (
            f"Expected exit 1 (bin/add_project.py no-arg Usage), got {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


@requires_symlink
class TestINT9:
    """INT-9: mai health — exit code == 2 with broken project symlink (D1 override).

    USER DECISION OVERRIDE D1: mesh/commands/scripts/project_health.py WILL be changed
    so main() returns/exits an int: 0 healthy / 1 issues / 2 broken, with sys.exit(main())
    in __main__. Tests assert NON-ZERO == 2 for broken symlink.
    """

    def test_health_broken_symlink_returncode_2(self, tmp_path):
        """INT-9: mai health against a workspace WITH a broken project symlink returns 2 (broken).

        D1 override: returncode MUST be 2 (not always 0 as the original spec said).
        When project_health.py is updated per D1, this test will go GREEN.
        Until then it is RED (expected — TDD).
        """
        ws = _make_fake_ws(tmp_path)
        projects_dir = ws / "projects"
        projects_dir.mkdir(exist_ok=True)
        # Create a dangling symlink (target does not exist)
        broken_link = projects_dir / "broken-proj"
        broken_link.symlink_to(str(tmp_path / "nonexistent_target"))

        result = _run_cli("health", root=ws)
        assert result.returncode == 2, (
            f"Expected returncode == 2 (broken) per D1 override, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}\n"
            "NOTE: project_health.py must be updated by the implementer to exit 2 on broken links."
        )

    def test_health_broken_symlink_report_in_stdout(self, tmp_path):
        """INT-9: stdout contains 'Project Health Report'."""
        ws = _make_fake_ws(tmp_path)
        projects_dir = ws / "projects"
        projects_dir.mkdir(exist_ok=True)
        broken_link = projects_dir / "broken-proj"
        broken_link.symlink_to(str(tmp_path / "nonexistent_target"))

        result = _run_cli("health", root=ws)
        assert "Project Health Report" in result.stdout, (
            f"Expected 'Project Health Report' in stdout: {result.stdout!r}"
        )

    def test_health_broken_symlink_in_stdout_text(self, tmp_path):
        """INT-9: stdout contains 'Broken symlink' for the offending project."""
        ws = _make_fake_ws(tmp_path)
        projects_dir = ws / "projects"
        projects_dir.mkdir(exist_ok=True)
        broken_link = projects_dir / "broken-proj"
        broken_link.symlink_to(str(tmp_path / "nonexistent_target"))

        result = _run_cli("health", root=ws)
        assert "Broken symlink" in result.stdout, (
            f"Expected 'Broken symlink' in stdout: {result.stdout!r}"
        )

    def test_health_healthy_workspace_returncode_0(self, tmp_path):
        """INT-9: A healthy workspace exits 0."""
        ws = _make_fake_ws(tmp_path)
        # No projects — empty workspace
        result = _run_cli("health", root=ws)
        assert result.returncode == 0, (
            f"Expected exit 0 for healthy workspace, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


@requires_symlink
class TestINT10:
    """INT-10: mai add then mai list round-trip (privileged) reflects a linked project."""

    def test_add_then_list_roundtrip(self, tmp_path):
        """INT-10: add returns 0 and creates symlink; list then shows the project."""
        ws = _make_fake_ws(tmp_path)
        target_repo = tmp_path / "my-actual-repo"
        target_repo.mkdir()

        add_result = _run_cli("add", "myproject", str(target_repo), root=ws)
        assert add_result.returncode == 0, (
            f"mai add failed.\nstdout: {add_result.stdout!r}\nstderr: {add_result.stderr!r}"
        )

        link = ws / "projects" / "myproject"
        assert link.is_symlink(), f"Expected symlink at {link}"

        list_result = _run_cli("list", root=ws)
        assert list_result.returncode == 0, (
            f"mai list failed.\nstdout: {list_result.stdout!r}\nstderr: {list_result.stderr!r}"
        )
        assert "myproject" in list_result.stdout, (
            f"Expected 'myproject' in list output: {list_result.stdout!r}"
        )


class TestINT11:
    """INT-11: mai does not crash on a cp1252 console (child-routing paths)."""

    def test_list_cp1252_no_crash(self, tmp_path):
        """INT-11: 'mai list' under cp1252 — no UnicodeEncodeError, no Traceback."""
        ws = _make_fake_ws(tmp_path)
        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "list"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=_cli_env(ws, encoding="cp1252"),
            timeout=20,
        )
        assert result.returncode == 0, (
            f"Crashed under cp1252.\nstderr: {result.stderr!r}"
        )
        assert "Traceback" not in result.stderr
        assert "UnicodeEncodeError" not in result.stderr

    def test_health_cp1252_no_crash(self, tmp_path):
        """INT-11: 'mai health' under cp1252 — no UnicodeEncodeError, no Traceback."""
        ws = _make_fake_ws(tmp_path)
        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "health"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=_cli_env(ws, encoding="cp1252"),
            timeout=20,
        )
        assert result.returncode == 0, (
            f"Crashed under cp1252.\nstderr: {result.stderr!r}"
        )
        assert "Traceback" not in result.stderr
        assert "UnicodeEncodeError" not in result.stderr

    def test_help_cp1252_no_crash(self, tmp_path):
        """INT-11: 'mai --help' under cp1252 — no UnicodeEncodeError, no Traceback."""
        ws = _make_fake_ws(tmp_path)
        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "--help"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=_cli_env(ws, encoding="cp1252"),
            timeout=20,
        )
        assert result.returncode == 0, (
            f"Crashed under cp1252.\nstderr: {result.stderr!r}"
        )
        assert "Traceback" not in result.stderr
        assert "UnicodeEncodeError" not in result.stderr


@requires_symlink
class TestINT12:
    """INT-12: mai init scaffolds a fresh ROOT (privileged); unprivileged exit-2 path documented.

    Note: init returns 2 WITHOUT symlink privilege (verified init.py:333), which is
    indistinguishable from router-2 — the exit-code overload is explicitly documented.
    Cross-reference: exit-code-overload doubt #4.
    """

    def test_init_resolves_to_bin_init(self):
        """INT-12: VERBS['init'] target resolves to bin/init.py."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        rel = maicelium_cli.VERBS["init"]["rel_path"]
        assert rel == "bin/init.py", f"Expected bin/init.py, got {rel!r}"

    def test_init_on_fresh_tmp_root(self, tmp_path):
        """INT-12: mai init on a fresh tmp ROOT returns 0 and creates expected scaffolding."""
        ws = tmp_path / "fresh_ws"
        ws.mkdir()

        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "init"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_cli_env(ws), timeout=60,
        )
        assert result.returncode == 0, (
            f"mai init failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        # Verify some expected scaffolding was created
        created = [
            (ws / "mAIcelium.code-workspace").exists(),
            (ws / "WORKSPACE.md").exists(),
        ]
        assert any(created), (
            f"Expected init to create workspace files. ws contents: {list(ws.iterdir())}"
        )


class TestINT13:
    """INT-13: mai sync passes through child exit codes 2 AND 3 verbatim.

    ADVERSARIAL MUST-FIX #3. VERIFIED: sync_symlinks returns 2 (line 927) and 3 (line 981).
    Exit 2 is OVERLOADED: router-usage error AND child sync error AND init no-privilege.
    Cross-reference: doubt #4 (whether to remap router errors off 2).
    """

    def test_sync_passthrough_rc2(self, monkeypatch, tmp_path):
        """INT-13: mai sync passthrough of child returncode 2 (unit-level)."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))

        def fake_run(cmd, **kwargs):
            class FakeResult:
                returncode = 2
            return FakeResult()

        monkeypatch.setattr(maicelium_cli.subprocess, "run", fake_run)
        rc = maicelium_cli.dispatch("sync", [], str(ws))
        assert rc == 2, f"Expected passthrough of child rc=2, got {rc}"

    def test_sync_passthrough_rc3(self, monkeypatch, tmp_path):
        """INT-13: mai sync passthrough of child returncode 3 (unit-level).

        VERIFIED: sync_symlinks.py:981 returns 3 on degraded workspace.
        Router must NOT remap child-3 to anything else.
        """
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))

        def fake_run(cmd, **kwargs):
            class FakeResult:
                returncode = 3
            return FakeResult()

        monkeypatch.setattr(maicelium_cli.subprocess, "run", fake_run)
        rc = maicelium_cli.dispatch("sync", [], str(ws))
        assert rc == 3, f"Expected passthrough of child rc=3, got {rc}"

    def test_sync_check_only_no_symlink_privilege_returncode_2(self, tmp_path):
        """INT-13: sync --check-only under no-symlink exits 2 (child's, not router's).

        Note: exit 2 is OVERLOADED (router-2 AND child-sync-2 AND init-2 are identical).
        This test documents the overlap. Doubt #4 is whether to remap router errors off 2.
        """
        ws = _make_fake_ws(tmp_path)
        result = _run_cli("sync", "--check-only", root=ws)
        # 0 = no drift, 1 = drift, 2 = no symlink privilege (or router error, indistinguishable)
        assert result.returncode in (0, 1, 2), (
            f"Unexpected returncode {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


class TestINT14:
    """INT-14: mai with no resolvable root exits 2 with an actionable message."""

    def test_no_root_exits_2(self, tmp_path):
        """INT-14: No resolvable root (no --root, no env, cwd + __file__ dir both lack the
        marker) -> exit 2."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        no_ws_dir = tmp_path / "no_workspace"
        no_ws_dir.mkdir()
        fake_cli = no_ws_dir / "maicelium_cli.py"  # no bin/_bootstrap.py+mesh/ here

        with pytest.raises(SystemExit) as exc_info:
            maicelium_cli.resolve_root_for_cli(
                args=["list"],
                env={},
                cwd=str(no_ws_dir),
                file=str(fake_cli),
            )
        assert exc_info.value.code == 2

    def test_no_root_message_actionable(self, tmp_path, capsys):
        """INT-14: The no-root error message is actionable and names MAICELIUM_ROOT and --root."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        no_ws_dir = tmp_path / "no_workspace"
        no_ws_dir.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            maicelium_cli.resolve_root_for_cli(
                args=["list"],
                env={},
                cwd=str(no_ws_dir),
                file=str(no_ws_dir / "maicelium_cli.py"),  # __file__ fallback dir lacks the marker
            )
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        message = captured.out + captured.err
        assert "MAICELIUM_ROOT" in message
        assert "--root" in message


class TestINT15:
    """INT-15: Router-level error path is cp1252-safe (unknown verb under cp1252)."""

    def test_unknown_verb_cp1252_returncode_2(self, tmp_path):
        """INT-15: 'mai frobnicate' under PYTHONIOENCODING=cp1252 exits 2."""
        ws = _make_fake_ws(tmp_path)
        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "frobnicate"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=_cli_env(ws, encoding="cp1252"),
            timeout=20,
        )
        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

    def test_unknown_verb_cp1252_no_unicode_error(self, tmp_path):
        """INT-15: No UnicodeEncodeError or Traceback under cp1252."""
        ws = _make_fake_ws(tmp_path)
        result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "frobnicate"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=_cli_env(ws, encoding="cp1252"),
            timeout=20,
        )
        assert "Traceback" not in result.stderr, (
            f"Got Traceback under cp1252: {result.stderr!r}"
        )
        assert "UnicodeEncodeError" not in result.stderr, (
            f"Got UnicodeEncodeError under cp1252: {result.stderr!r}"
        )


# ===========================================================================
# PACKAGING TESTS
# ===========================================================================


class TestPK1:
    """PK-1: pyproject declares an installable distribution with the mai entry point."""

    def _load_pyproject(self):
        pyproject = REPO_ROOT / "pyproject.toml"
        with pyproject.open("rb") as fh:
            return tomllib.load(fh)

    def test_build_system_present(self):
        """PK-1: [build-system].build-backend == 'setuptools.build_meta'."""
        data = self._load_pyproject()
        bs = data.get("build-system", {})
        assert bs.get("build-backend") == "setuptools.build_meta", (
            f"Expected setuptools.build_meta, got {bs.get('build-backend')!r}"
        )

    def test_build_system_requires_setuptools(self):
        """PK-1: [build-system].requires contains setuptools>=68."""
        data = self._load_pyproject()
        requires = data.get("build-system", {}).get("requires", [])
        assert any("setuptools" in r for r in requires), (
            f"Expected setuptools in build-system.requires: {requires}"
        )

    def test_project_name_maicelium(self):
        """PK-1: [project].name == 'maicelium'."""
        data = self._load_pyproject()
        assert data.get("project", {}).get("name") == "maicelium", (
            f"Expected project.name == 'maicelium', got {data.get('project', {}).get('name')!r}"
        )

    def test_project_requires_python_311(self):
        """PK-1: [project].requires-python permits 3.11."""
        data = self._load_pyproject()
        req_py = data.get("project", {}).get("requires-python", "")
        assert "3.11" in req_py or ">=" in req_py, (
            f"Expected requires-python to cover 3.11, got {req_py!r}"
        )

    def test_project_dynamic_version(self):
        """PK-1: [project].dynamic == ['version'] (CRITICAL: prevents metadata-generation-failed)."""
        data = self._load_pyproject()
        dynamic = data.get("project", {}).get("dynamic", [])
        assert "version" in dynamic, (
            f"Expected 'version' in project.dynamic: {dynamic}. "
            "Without this, setuptools 68 fails: 'project must contain version properties'."
        )

    def test_dynamic_version_attr(self):
        """PK-1: [tool.setuptools.dynamic].version.attr == 'maicelium_cli.__version__'."""
        data = self._load_pyproject()
        dyn = data.get("tool", {}).get("setuptools", {}).get("dynamic", {})
        version_attr = dyn.get("version", {}).get("attr")
        assert version_attr == "maicelium_cli.__version__", (
            f"Expected attr='maicelium_cli.__version__', got {version_attr!r}"
        )

    def test_project_scripts_mai_entry_point(self):
        """PK-1: [project.scripts].mai == 'maicelium_cli:main'."""
        data = self._load_pyproject()
        scripts = data.get("project", {}).get("scripts", {})
        assert scripts.get("mai") == "maicelium_cli:main", (
            f"Expected 'maicelium_cli:main', got {scripts.get('mai')!r}"
        )

    def test_setuptools_py_modules_not_packages_find(self):
        """PK-1: [tool.setuptools].py-modules contains 'maicelium_cli'; no packages=find:."""
        data = self._load_pyproject()
        ts = data.get("tool", {}).get("setuptools", {})
        py_modules = ts.get("py-modules", [])
        assert "maicelium_cli" in py_modules, (
            f"Expected 'maicelium_cli' in tool.setuptools.py-modules: {py_modules}"
        )
        packages = ts.get("packages")
        assert packages is None or packages != {"find": {}}, (
            "packages=find: is FORBIDDEN (would package bin/, mesh/, tests/)"
        )

    def test_pytest_config_not_clobbered(self):
        """PK-1: [tool.pytest.ini_options] still has strict_markers, requires_symlink, testpaths."""
        data = self._load_pyproject()
        ini = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        assert ini.get("strict_markers") is True
        markers = ini.get("markers", [])
        assert any("requires_symlink" in m for m in markers), (
            f"requires_symlink marker missing: {markers}"
        )
        assert ini.get("testpaths") == ["tests"]


class TestPK2:
    """PK-2: Version is single-sourced and matches maicelium_cli.__version__."""

    def test_no_static_version_in_project(self):
        """PK-2: [project] has NO static version key; version is dynamic."""
        with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        project = data.get("project", {})
        assert "version" not in project, (
            "project.version must NOT be static — version is single-sourced via dynamic attr."
        )

    def test_maicelium_cli_version_attr(self):
        """PK-2: import maicelium_cli; __version__ is a non-empty str."""
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli

        assert hasattr(maicelium_cli, "__version__")
        assert isinstance(maicelium_cli.__version__, str)
        assert maicelium_cli.__version__, "maicelium_cli.__version__ must not be empty"

    def test_dynamic_attr_matches_module_version(self):
        """PK-2: [tool.setuptools.dynamic].version.attr == 'maicelium_cli.__version__'."""
        with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        dyn = data.get("tool", {}).get("setuptools", {}).get("dynamic", {})
        assert dyn.get("version", {}).get("attr") == "maicelium_cli.__version__"


class TestPK3:
    """PK-3: import contract: maicelium_cli exposes main(argv)->int with the bin-script shape."""

    def _import_cli(self):
        import sys as _sys
        if "maicelium_cli" in _sys.modules:
            del _sys.modules["maicelium_cli"]
        import maicelium_cli
        return maicelium_cli

    def test_main_is_callable(self, tmp_path, monkeypatch):
        """PK-3: maicelium_cli.main is callable."""
        cli = self._import_cli()
        assert callable(cli.main)

    def test_main_empty_returns_0(self, monkeypatch, tmp_path):
        """PK-3: main([]) returns int 0."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        rc = cli.main([])
        assert isinstance(rc, int), f"Expected int, got {type(rc)}"
        assert rc == 0

    def test_version_is_str(self):
        """PK-3: maicelium_cli.__version__ is a non-empty str."""
        cli = self._import_cli()
        assert isinstance(cli.__version__, str)
        assert cli.__version__

    def test_verbs_is_nonempty_mapping(self):
        """PK-3: maicelium_cli.VERBS is a non-empty mapping."""
        cli = self._import_cli()
        assert hasattr(cli, "VERBS")
        assert len(cli.VERBS) > 0

    def test_main_version_returns_0(self, monkeypatch, tmp_path):
        """PK-3: main(['--version']) returns 0."""
        cli = self._import_cli()
        ws = _make_fake_ws(tmp_path)
        monkeypatch.setenv("MAICELIUM_ROOT", str(ws))
        monkeypatch.setattr(cli, "dispatch", lambda *a, **kw: 0)

        rc = cli.main(["--version"])
        assert rc == 0


@pytest.mark.install
class TestPK4:
    """PK-4: Real `pip install -e .` succeeds — contract test cannot pass over unbuildable pyproject."""

    def test_pip_install_editable_succeeds(self, tmp_path):
        """PK-4: pip install -e . in an isolated venv exits 0.

        ADVERSARIAL MUST-FIX #2: tomllib-only PK-1 cannot prove the package is installable.
        This test actually builds and installs it.
        """
        venv_dir = tmp_path / "venv"
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, f"venv creation failed: {result.stderr}"

        # Use the venv's python to install
        if sys.platform == "win32":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        install_result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-e", str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120,
        )
        assert install_result.returncode == 0, (
            f"pip install -e . failed.\n"
            f"stdout: {install_result.stdout!r}\n"
            f"stderr: {install_result.stderr!r}"
        )

    def test_installed_mai_version(self, tmp_path):
        """PK-4: Installed `mai --version` from outside the repo exits 0 and prints version."""
        venv_dir = tmp_path / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, check=True,
        )

        if sys.platform == "win32":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-e", str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, check=True,
        )

        outside_cwd = tmp_path / "outside"
        outside_cwd.mkdir()

        env = os.environ.copy()
        env["MAICELIUM_ROOT"] = str(tmp_path / "ws")
        (tmp_path / "ws").mkdir()

        result = subprocess.run(
            [str(venv_python), "-c",
             "import maicelium_cli; import sys; sys.exit(maicelium_cli.main(['--version']))"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(outside_cwd), env=env, timeout=30,
        )
        assert result.returncode == 0, (
            f"Installed mai --version failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


@pytest.mark.install
class TestPK5:
    """PK-5: Wheel builds without packaging bin/, mesh/, tests/."""

    def test_wheel_build_succeeds(self, tmp_path):
        """PK-5: python -m build exits 0 and creates a wheel."""
        dist_dir = tmp_path / "dist"
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir), str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Wheel build failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        wheels = list(dist_dir.glob("*.whl"))
        assert wheels, "No wheel file found in dist dir"

    def test_wheel_does_not_contain_bin_lib(self, tmp_path):
        """PK-5: Wheel does NOT contain bin/_lib/*.py (tripwire against packages=find:)."""
        import zipfile

        dist_dir = tmp_path / "dist"
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir), str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120, check=True,
        )
        wheel = next(dist_dir.glob("*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            names = zf.namelist()
        bin_lib_files = [n for n in names if "bin/_lib" in n or "bin\\_lib" in n]
        assert not bin_lib_files, (
            f"Wheel contains bin/_lib files (packages=find: regression): {bin_lib_files}"
        )

    def test_wheel_contains_maicelium_cli(self, tmp_path):
        """PK-5: Wheel contains maicelium_cli (the single py-module)."""
        import zipfile

        dist_dir = tmp_path / "dist"
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir), str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120, check=True,
        )
        wheel = next(dist_dir.glob("*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            names = zf.namelist()
        assert any("maicelium_cli" in n for n in names), (
            f"maicelium_cli not found in wheel contents: {names}"
        )


@pytest.mark.install
class TestPK6:
    """PK-6: No build artifacts dirty the tree after install/wheel tests."""

    def test_gitignore_covers_build_artifacts(self):
        """PK-6: .gitignore contains entries covering build/, dist/, and *.egg-info."""
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists(), ".gitignore must exist"
        content = gitignore.read_text(encoding="utf-8")
        assert "build/" in content or "build" in content, (
            "build/ must be in .gitignore"
        )
        assert "dist/" in content or "dist" in content, (
            "dist/ must be in .gitignore"
        )
        assert ".egg-info" in content or "egg-info" in content, (
            "*.egg-info must be in .gitignore"
        )

    def test_git_status_clean_after_install(self, tmp_path):
        """PK-6: git status --porcelain shows no untracked build/dist/egg-info artifacts."""
        # Run pip install -e . and check that build artifacts are gitignored
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(REPO_ROOT)],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120, cwd=str(REPO_ROOT),
        )

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT), timeout=30,
        )
        untracked = [
            line for line in result.stdout.splitlines()
            if any(x in line for x in ["build/", "dist/", ".egg-info", "egg-info/"])
        ]
        assert not untracked, (
            f"Build artifacts not gitignored, tree is dirty: {untracked}"
        )


# ===========================================================================
# SHIM TESTS
# ===========================================================================


class TestSH1:
    """SH-1: Committed mai / mai.cmd shims delegate to maicelium_cli (single source, not a fork)."""

    def test_mai_shim_is_executable(self):
        """SH-1: ./mai is executable and has a python shebang."""
        mai_shim = REPO_ROOT / "mai"
        assert mai_shim.exists(), "mai shim must exist at repo root"
        if sys.platform != "win32":
            assert os.access(str(mai_shim), os.X_OK), "mai shim must be executable"
            content = mai_shim.read_text(encoding="utf-8")
            assert "python" in content.lower() or "#!" in content, (
                "mai shim must have a python shebang"
            )

    def test_mai_cmd_references_maicelium_cli(self):
        """SH-1: mai.cmd references maicelium_cli.py and forwards %*."""
        mai_cmd = REPO_ROOT / "mai.cmd"
        assert mai_cmd.exists(), "mai.cmd must exist at repo root"
        content = mai_cmd.read_text(encoding="utf-8")
        assert "maicelium_cli.py" in content, (
            "mai.cmd must reference maicelium_cli.py"
        )
        assert "%*" in content, "mai.cmd must forward %* (all arguments)"

    def test_mai_cmd_no_verb_dispatch_logic(self):
        """SH-1: mai.cmd contains NO verb-dispatch logic (single-source invariant)."""
        mai_cmd = REPO_ROOT / "mai.cmd"
        assert mai_cmd.exists(), "mai.cmd must exist at repo root"
        content = mai_cmd.read_text(encoding="utf-8")
        # The shim must not contain per-verb routing
        verb_patterns = ["bin/add_project", "bin/remove_project", "bin/init.py",
                         "bin/sync_symlinks", "if '%1'=="]
        for pattern in verb_patterns:
            assert pattern not in content, (
                f"mai.cmd contains verb-dispatch logic ('{pattern}') — single-source violated"
            )

    def test_mai_shim_version_equals_cli_version(self, tmp_path):
        """SH-1: the committed shim's --version equals `python maicelium_cli.py --version`.

        Runs the platform-appropriate committed shim (mai.cmd via `cmd /c` on Windows,
        the ./mai POSIX shim elsewhere) so the check holds on every runner WITHOUT
        skipping -- an unconditional Windows skip would trip the privileged skip-guard.
        """
        ws = _make_fake_ws(tmp_path)
        env = _cli_env(ws)

        if sys.platform == "win32":
            shim = REPO_ROOT / "mai.cmd"
            assert shim.exists(), "mai.cmd shim is missing"
            shim_cmd = ["cmd", "/c", str(shim), "--version"]
        else:
            shim = REPO_ROOT / "mai"
            assert shim.exists(), "mai shim is missing"
            shim_cmd = [str(shim), "--version"]

        shim_result = subprocess.run(
            shim_cmd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=20,
        )
        cli_result = subprocess.run(
            [sys.executable, str(MAICELIUM_CLI_PY), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=20,
        )
        assert shim_result.returncode == 0, (
            f"shim failed: rc={shim_result.returncode}\n"
            f"stdout={shim_result.stdout!r}\nstderr={shim_result.stderr!r}"
        )
        assert shim_result.stdout.strip() == cli_result.stdout.strip(), (
            f"Shim version: {shim_result.stdout!r}\n"
            f"CLI version:  {cli_result.stdout!r}"
        )


# ===========================================================================
# CI / MARKER TESTS
# ===========================================================================


class TestCI1:
    """CI-1: New 'install' marker is registered (strict_markers regression)."""

    def test_install_marker_in_pyproject(self):
        """CI-1: pyproject.toml markers list contains an entry starting 'install:'."""
        with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
        assert any(m.startswith("install:") or m.startswith("install ") for m in markers), (
            f"'install' marker not registered in pyproject.toml markers: {markers}\n"
            "strict_markers is ON — unregistered markers cause collection failure."
        )

    def test_requires_symlink_still_registered(self):
        """CI-1: requires_symlink marker still registered (not clobbered)."""
        with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
        assert any("requires_symlink" in m for m in markers), (
            f"requires_symlink marker missing from pyproject.toml: {markers}"
        )

    def test_pytest_markers_lists_install(self):
        """CI-1: subprocess 'pytest --markers' lists the install marker."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--markers"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT), timeout=30,
        )
        assert result.returncode == 0
        assert "install" in result.stdout, (
            f"'install' not in pytest --markers output:\n{result.stdout}"
        )

    def test_collect_only_test_mai_cli_exits_0(self):
        """CI-1: collect-only of tests/test_mai_cli.py exits 0 (no unknown-marker error)."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             str(TESTS_DIR / "test_mai_cli.py")],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT), timeout=60,
        )
        assert result.returncode == 0, (
            f"collect-only failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


class TestCI2:
    """CI-2: CLI tests integrate with both CI jobs and respect the skip-guard."""

    def test_mai_cli_discoverable_under_testpaths(self):
        """CI-2: tests/test_mai_cli.py is discoverable under testpaths=['tests']."""
        assert (TESTS_DIR / "test_mai_cli.py").exists(), (
            "test_mai_cli.py must exist under tests/ (testpaths in pyproject.toml)"
        )

    def test_symlink_tests_use_requires_symlink(self):
        """CI-2: Every symlink-gated test imports requires_symlink from _marks."""
        content = (TESTS_DIR / "test_mai_cli.py").read_text(encoding="utf-8")
        assert "from _marks import requires_symlink" in content, (
            "tests/test_mai_cli.py must import requires_symlink from _marks"
        )
        assert "@requires_symlink" in content, (
            "tests/test_mai_cli.py must apply @requires_symlink to symlink-gated tests"
        )

    def test_no_unconditional_skip_in_cli_tests(self):
        """CI-2: No unconditional skip/xfail in test_mai_cli.py.

        Unconditional skips trip the privileged skip-guard (which counts xfail as
        skipped). This catches BOTH skip/xfail decorators AND bare skip()/xfail()
        calls in a test body. Skips guarded by an if/elif (e.g. platform gates) are
        allowed because they do not fire on the privileged Linux runner. Hardened
        after an unconditional body-level skip in INT-14 slipped past the
        decorator-only check and reddened the CI matrix.
        """
        lines = (TESTS_DIR / "test_mai_cli.py").read_text(encoding="utf-8").splitlines()

        def _prev_code_line(idx):
            j = idx - 1
            while j >= 0:
                s = lines[j].strip()
                if s and not s.startswith("#"):
                    return s
                j -= 1
            return ""

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("@pytest.mark.skip") or stripped.startswith("@pytest.mark.xfail"):
                pytest.fail(
                    f"Unconditional skip/xfail decorator at line {i + 1}: {line!r}\n"
                    "This would trip the privileged skip-guard."
                )
            if stripped.startswith("pytest.skip(") or stripped.startswith("pytest.xfail("):
                prev = _prev_code_line(i)
                if not (prev.startswith("if ") or prev.startswith("elif ")):
                    pytest.fail(
                        f"Unconditional pytest.skip()/xfail() at line {i + 1}: {line!r}\n"
                        "Guard it with an if/elif (e.g. a platform gate) or remove it -- "
                        "it would trip the privileged skip-guard."
                    )

    def test_install_marked_tests_can_be_deselected(self):
        """CI-2: install-marked tests are deselected by -m 'not install' (not counted as skipped)."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "-m", "not install",
             str(TESTS_DIR / "test_mai_cli.py")],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT), timeout=60,
        )
        assert result.returncode == 0, (
            f"collect-only with -m 'not install' failed.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        # PK-4, PK-5, PK-6 tests should NOT appear
        for install_class in ["TestPK4", "TestPK5", "TestPK6"]:
            assert install_class not in result.stdout, (
                f"{install_class} appears in 'not install' collection — marker not applied?"
            )
