"""Tests for _lib.symlinks."""
import os

from _lib.symlinks import detect_junction, find_broken_symlinks


def test_find_broken_symlinks_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "nope"
    assert find_broken_symlinks(str(missing)) == []


def test_find_broken_symlinks_detects_dangling(tmp_path):
    link = tmp_path / "dangling"
    os.symlink("/no/such/path/exists", str(link))

    broken = find_broken_symlinks(str(tmp_path))

    assert str(link) in broken


def test_find_broken_symlinks_ignores_valid(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("ok")
    link = tmp_path / "good_link"
    os.symlink(str(real), str(link))

    broken = find_broken_symlinks(str(tmp_path))

    assert str(link) not in broken


def test_find_broken_symlinks_respects_maxdepth(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    link = deep / "dangling"
    os.symlink("/no/such/target", str(link))

    broken_shallow = find_broken_symlinks(str(tmp_path), maxdepth=2)
    broken_deep = find_broken_symlinks(str(tmp_path), maxdepth=5)

    assert str(link) not in broken_shallow
    assert str(link) in broken_deep


def test_detect_junction_false_on_linux(tmp_path):
    real = tmp_path / "dir"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(str(real), str(link))

    assert detect_junction(str(real)) is False
    assert detect_junction(str(link)) is False
    assert detect_junction(str(tmp_path / "missing")) is False
