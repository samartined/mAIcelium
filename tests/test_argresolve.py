"""Tests for bin/_lib/argresolve.py — either-order (path/name) resolution.

The helper decides which positional is the path and which is the name by asking
"is this an existing directory?" (resolved relative to cwd, so a bare folder name
with no slash works), using name-shape (bare identifier) to break a tie, and
raising AmbiguousArgsError when both are existing directories AND both look like
bare names. Explicit --path/--name flags always win.
"""
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from _lib.argresolve import AmbiguousArgsError, resolve_name_and_path  # noqa: E402


def test_exactly_one_existing_dir_name_first(tmp_path):
    """Classic order: name then existing path."""
    d = tmp_path / "repo"
    d.mkdir()
    name, path = resolve_name_and_path(["demo", str(d)])
    assert name == "demo"
    assert path == str(d)


def test_exactly_one_existing_dir_path_first(tmp_path):
    """New order: existing path then name."""
    d = tmp_path / "repo"
    d.mkdir()
    name, path = resolve_name_and_path([str(d), "demo"])
    assert name == "demo"
    assert path == str(d)


def test_bare_cwd_folder_no_slash(tmp_path, monkeypatch):
    """A folder in the current directory, written WITHOUT a slash, is recognised as the path."""
    d = tmp_path / "repo"
    d.mkdir()
    monkeypatch.chdir(tmp_path)
    name, path = resolve_name_and_path(["repo", "demo"])  # path first, bare
    assert name == "demo"
    assert path == "repo"


def test_both_dirs_slash_disambiguates(tmp_path, monkeypatch):
    """Both exist as dirs, but one is written with a slash/dot -> it's the path, the bare one the name."""
    (tmp_path / "backup").mkdir()
    (tmp_path / "mirepo").mkdir()
    monkeypatch.chdir(tmp_path)
    name, path = resolve_name_and_path(["backup", "./mirepo"])
    assert name == "backup"
    assert path == "./mirepo"


def test_both_bare_existing_dirs_raises(tmp_path, monkeypatch):
    """The true tie: both are bare identifiers AND both exist as dirs -> ambiguous."""
    (tmp_path / "backup").mkdir()
    (tmp_path / "mirepo").mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AmbiguousArgsError):
        resolve_name_and_path(["backup", "mirepo"])


def test_neither_exists_slash_picks_path(tmp_path):
    """Neither exists: the slash-shaped token is the path (so the error names the real path)."""
    name, path = resolve_name_and_path(["demo", "/no/such/dir"])
    assert name == "demo"
    assert path == "/no/such/dir"


def test_neither_exists_both_bare_classic_order(tmp_path):
    """Neither exists and both bare: fall back to the classic order (name first, path second)."""
    name, path = resolve_name_and_path(["alpha", "beta"])
    assert name == "alpha"
    assert path == "beta"


def test_flags_override_both(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    name, path = resolve_name_and_path([], name_flag="demo", path_flag=str(d))
    assert name == "demo"
    assert path == str(d)


def test_lone_path_flag_pairs_with_positional(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    name, path = resolve_name_and_path(["demo"], path_flag=str(d))
    assert name == "demo"
    assert path == str(d)


def test_lone_name_flag_pairs_with_positional(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    name, path = resolve_name_and_path([str(d)], name_flag="demo")
    assert name == "demo"
    assert path == str(d)


def test_wrong_positional_count_raises_valueerror():
    with pytest.raises(ValueError):
        resolve_name_and_path(["only-one"])
    with pytest.raises(ValueError):
        resolve_name_and_path(["a", "b", "c"])
