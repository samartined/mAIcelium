"""Tests proving TR-9: requires_symlink is a registered pytest marker.

Uses subprocess so --strict-markers is applied under the real repo config
(pyproject.toml) without affecting the current test session.
"""
import subprocess
import sys
import textwrap


def test_unknown_marker_errors_under_strict_markers(tmp_path):
    """An unregistered marker must cause collection failure under --strict-markers."""
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
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--strict-markers", "-q", str(test_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0, (
        "Expected non-zero exit for unknown marker under --strict-markers, "
        f"got 0.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "marker" in combined.lower(), (
        f"Expected 'marker' in output.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_requires_symlink_is_registered_marker():
    """requires_symlink must appear in the configured markers list."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"pytest --markers failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "requires_symlink" in result.stdout, (
        f"requires_symlink not found in registered markers.\n{result.stdout}"
    )
