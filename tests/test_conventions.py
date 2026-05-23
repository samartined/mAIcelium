"""Tests for bin/_lib/conventions.py."""
import json
import os

from _lib.conventions import DEFAULT_CONVENTIONS, load_conventions


def test_missing_file_returns_defaults(tmp_path):
    root = str(tmp_path)
    out = load_conventions(root)
    assert out == DEFAULT_CONVENTIONS
    # Must be a new dict (no shared mutable default)
    out["project_data_dir"] = "modified"
    assert DEFAULT_CONVENTIONS["project_data_dir"] == ".cursor"


def test_load_overrides_data_dir(tmp_path):
    root = str(tmp_path)
    mesh = os.path.join(root, "mesh")
    os.makedirs(mesh)
    with open(os.path.join(mesh, "conventions.json"), "w") as f:
        json.dump({"project_data_dir": ".vscode"}, f)
    out = load_conventions(root)
    assert out["project_data_dir"] == ".vscode"
    # Other keys retain defaults
    assert out["project_rules_subdir"] == "rules"
    assert out["project_data_subdirs"] == DEFAULT_CONVENTIONS["project_data_subdirs"]


def test_load_full_overrides(tmp_path):
    root = str(tmp_path)
    mesh = os.path.join(root, "mesh")
    os.makedirs(mesh)
    custom = {
        "project_data_dir": ".custom",
        "project_data_subdirs": ["a", "b"],
        "project_rules_subdir": "r",
        "project_skills_subdirs": ["s"],
    }
    with open(os.path.join(mesh, "conventions.json"), "w") as f:
        json.dump(custom, f)
    assert load_conventions(root) == custom
