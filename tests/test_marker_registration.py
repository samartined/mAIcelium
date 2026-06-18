"""Tests proving TR-9: requires_symlink is a registered pytest marker.

Uses subprocess so the test validates the ACTUAL repo config path (pyproject.toml),
NOT --strict-markers passed explicitly on the CLI.  A test that passes --strict-markers
explicitly always works regardless of the repo config — that is the false-confidence
pattern this file is deliberately avoiding.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import tomllib


# Absolute path to the repo root so every subprocess runs against the real config.
REPO_ROOT = Path(__file__).parent.parent


def _write_bad_marker_test(tmp_path: Path) -> Path:
    """Return a throwaway test file that uses an unregistered marker."""
    test_file = tmp_path / "test_bad_marker.py"
    test_file.write_text(
        textwrap.dedent("""\
            import pytest

            @pytest.mark.requires_symlinkXX
            def test_dummy():
                pass
        """),
        encoding="utf-8",
    )
    return test_file


def test_strict_markers_ini_key_is_present():
    """pyproject.toml must set strict_markers = true in [tool.pytest.ini_options].

    This is the load-bearing config key.  --strict-markers in addopts is harmless
    but does NOT set the INI value that pytest 9 reads to enforce strict mode when
    no explicit CLI flag is given (i.e., the CI path).
    """
    pyproject = REPO_ROOT / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)

    ini_opts = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert ini_opts.get("strict_markers") is True, (
        "pyproject.toml [tool.pytest.ini_options] must have strict_markers = true. "
        "Without this key, pytest 9 does NOT enforce strict markers when the flag is "
        "absent from the explicit CLI call (e.g., in CI's `python -m pytest`)."
    )


def test_unknown_marker_errors_under_repo_config(tmp_path):
    """A typo'd marker must cause collection failure using ONLY the repo config.

    Critically, --strict-markers is NOT passed on the CLI here.  The test must
    fail (exit != 0) solely because strict_markers = true is set in pyproject.toml.
    If that ini key is removed, this test FAILS (subprocess exits 0, warning only).
    """
    test_file = _write_bad_marker_test(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(REPO_ROOT / "pyproject.toml"),
            "-q",
            str(test_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0, (
        "Expected non-zero exit for unknown marker under repo config "
        "(strict_markers = true in pyproject.toml), got 0.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "requires_symlinkXX" in combined or "marker" in combined.lower(), (
        f"Expected marker-related error in output.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_requires_symlink_is_registered_marker():
    """requires_symlink must appear in the configured markers list."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"pytest --markers failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "requires_symlink" in result.stdout, (
        f"requires_symlink not found in registered markers.\n{result.stdout}"
    )
