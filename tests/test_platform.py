"""Tests for _lib.platform."""
import os

from _lib.platform import create_link, is_windows, resolve_root


def test_resolve_root_returns_workspace_root():
    root = resolve_root()
    assert os.path.isdir(os.path.join(root, "bin", "_lib"))
    assert os.path.isfile(os.path.join(root, "CLAUDE.md"))


def test_is_windows_returns_bool():
    assert isinstance(is_windows(), bool)


def test_create_link_creates_symlink(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello")
    target = tmp_path / "link.txt"

    create_link(str(source), str(target))

    assert target.is_symlink()
    assert target.read_text() == "hello"


def test_create_link_replaces_existing(tmp_path):
    source_a = tmp_path / "a.txt"
    source_a.write_text("A")
    source_b = tmp_path / "b.txt"
    source_b.write_text("B")
    target = tmp_path / "link.txt"

    create_link(str(source_a), str(target))
    create_link(str(source_b), str(target))

    assert target.is_symlink()
    assert target.read_text() == "B"


def test_create_link_idempotent(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload")
    target = tmp_path / "link.txt"

    create_link(str(source), str(target))
    create_link(str(source), str(target))

    assert target.is_symlink()
    assert target.read_text() == "payload"
