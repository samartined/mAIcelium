"""Tests for bin/_lib/workspace_writer.py.

Each test operates against a tmp_path directory that contains WORKSPACE.md.
No scripts are invoked — the writer functions are tested directly.
"""
import os
import sys
import textwrap

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from _lib.workspace_writer import (  # noqa: E402
    add_project_entry,
    remove_project_entry,
    set_project_flag,
    add_layer_entry,
    remove_layer_entry,
    set_mcp_source,
    unset_mcp_source,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _wf(tmp_path):
    return tmp_path / "WORKSPACE.md"


def _write(tmp_path, text):
    _wf(tmp_path).write_text(textwrap.dedent(text))


def _read(tmp_path):
    return _wf(tmp_path).read_text()


# ── add_project_entry ────────────────────────────────────────────────────────


def test_add_project_creates_section_when_missing(tmp_path):
    """File does not exist -> WORKSPACE.md is created with a projects: section."""
    add_project_entry(str(tmp_path), "demo", "/opt/demo")
    content = _read(tmp_path)
    assert "projects:" in content
    assert "- name: demo" in content
    assert "path: /opt/demo" in content


def test_add_project_appends_to_existing_section(tmp_path):
    """A second project is appended below the first."""
    _write(
        tmp_path,
        """\
        # Active workspace

        projects:
        - name: alpha
          path: /opt/alpha
          added: 2024-01-01T00:00:00
        """,
    )
    add_project_entry(str(tmp_path), "beta", "/opt/beta")
    content = _read(tmp_path)
    assert "- name: alpha" in content
    assert "- name: beta" in content
    assert content.index("- name: alpha") < content.index("- name: beta")


def test_add_project_preserves_other_sections(tmp_path):
    """mesh_layers and mcp_source remain intact after adding a project."""
    _write(
        tmp_path,
        """\
        # Active workspace

        mesh_layers:
        - name: acme
          path: /opt/acme
          client: acme

        mcp_source:
          path: /opt/mcp

        projects:
        - name: alpha
          path: /opt/alpha
        """,
    )
    add_project_entry(str(tmp_path), "beta", "/opt/beta")
    content = _read(tmp_path)
    assert "mesh_layers:" in content
    assert "- name: acme" in content
    assert "mcp_source:" in content
    assert "path: /opt/mcp" in content
    assert "- name: beta" in content


def test_add_project_with_added_timestamp(tmp_path):
    """When added= is provided the field is written into the entry."""
    add_project_entry(str(tmp_path), "demo", "/opt/demo", added="2025-01-01T00:00:00+00:00")
    content = _read(tmp_path)
    assert "added: 2025-01-01T00:00:00+00:00" in content


def test_add_project_replaces_inline_empty_list(tmp_path):
    """projects: [] is replaced with a real section."""
    _write(
        tmp_path,
        """\
        # Active workspace

        projects: []
        """,
    )
    add_project_entry(str(tmp_path), "demo", "/opt/demo")
    content = _read(tmp_path)
    assert "projects: []" not in content
    assert "- name: demo" in content


# ── remove_project_entry ─────────────────────────────────────────────────────


def test_remove_project_removes_entry_and_continuation(tmp_path):
    """Removing an entry strips the name line and all indented fields."""
    _write(
        tmp_path,
        """\
        projects:
        - name: alpha
          path: /opt/alpha
          added: 2024-01-01
        - name: beta
          path: /opt/beta
        """,
    )
    remove_project_entry(str(tmp_path), "alpha")
    content = _read(tmp_path)
    assert "- name: alpha" not in content
    assert "path: /opt/alpha" not in content
    assert "added: 2024-01-01" not in content
    assert "- name: beta" in content
    assert "path: /opt/beta" in content


def test_remove_project_handles_blank_lines_in_entry(tmp_path):
    """BUG-01 regression: blank line inside entry block must be removed with the entry."""
    _write(
        tmp_path,
        """\
        projects:
        - name: alpha
          path: /opt/alpha

          added: 2024-01-01
        - name: beta
          path: /opt/beta
        """,
    )
    remove_project_entry(str(tmp_path), "alpha")
    content = _read(tmp_path)
    assert "- name: alpha" not in content
    assert "  added: 2024-01-01" not in content
    assert "- name: beta" in content
    assert "  path: /opt/beta" in content


def test_remove_project_nonexistent_is_idempotent(tmp_path):
    """Removing a name that is not present leaves the file unchanged."""
    original = "# Active workspace\n\nprojects:\n- name: alpha\n  path: /opt/alpha\n"
    _wf(tmp_path).write_text(original)
    remove_project_entry(str(tmp_path), "ghost")
    assert _read(tmp_path) == original


def test_remove_project_exact_match_not_prefix(tmp_path):
    """Verify that removing 'alpha' does NOT remove 'alpha-beta' (exact match)."""
    _write(
        tmp_path,
        """\
        projects:
        - name: alpha
          path: /a
        - name: alpha-beta
          path: /ab
        """,
    )
    remove_project_entry(str(tmp_path), "alpha")
    content = _read(tmp_path)
    assert "alpha-beta" in content
    assert "- name: alpha\n" not in content


def test_remove_project_preserves_following_entry(tmp_path):
    """After removing the first entry, the second one is fully intact."""
    _write(
        tmp_path,
        """\
        projects:
        - name: first
          path: /opt/first
          added: 2024-01-01
        - name: second
          path: /opt/second
          added: 2024-01-02
        """,
    )
    remove_project_entry(str(tmp_path), "first")
    content = _read(tmp_path)
    assert "- name: first" not in content
    assert "- name: second" in content
    assert "  path: /opt/second" in content
    assert "  added: 2024-01-02" in content


# ── set_project_flag ─────────────────────────────────────────────────────────


def test_set_project_flag_inserts_when_missing(tmp_path):
    """A flag not present in the entry is inserted after the last field."""
    _write(
        tmp_path,
        """\
        projects:
        - name: demo
          path: /opt/demo
          added: 2024-01-01
        """,
    )
    action, err = set_project_flag(str(tmp_path), "demo", "context_inline", "false")
    assert err == ""
    assert action == "added"
    content = _read(tmp_path)
    assert "context_inline: false" in content
    assert content.index("- name: demo") < content.index("context_inline: false")


def test_set_project_flag_updates_when_present(tmp_path):
    """An existing flag is updated in-place (no duplicate line)."""
    _write(
        tmp_path,
        """\
        projects:
        - name: demo
          path: /opt/demo
          context_inline: true
        """,
    )
    action, err = set_project_flag(str(tmp_path), "demo", "context_inline", "false")
    assert err == ""
    assert action == "updated"
    content = _read(tmp_path)
    assert content.count("context_inline:") == 1
    assert "context_inline: false" in content
    assert "context_inline: true" not in content


def test_set_project_flag_unknown_project_warns(tmp_path):
    """Unknown project name returns a non-empty error and does not modify file."""
    original = "projects:\n- name: demo\n  path: /opt/demo\n"
    _wf(tmp_path).write_text(original)
    action, err = set_project_flag(str(tmp_path), "ghost", "context_inline", "false")
    assert action is None
    assert "ghost" in err
    assert "not found" in err
    assert _read(tmp_path) == original


# ── add_layer_entry ──────────────────────────────────────────────────────────


def test_add_layer_creates_section(tmp_path):
    """When no mesh_layers: section exists, one is created before projects:."""
    _write(
        tmp_path,
        """\
        # Active workspace

        projects:
        - name: alpha
          path: /opt/alpha
        """,
    )
    add_layer_entry(str(tmp_path), "acme", "/opt/acme", client="acme")
    content = _read(tmp_path)
    assert "mesh_layers:" in content
    assert "- name: acme" in content
    assert "path: /opt/acme" in content
    assert "client: acme" in content
    assert content.index("mesh_layers:") < content.index("projects:")


def test_add_layer_with_client_and_repo(tmp_path):
    """client and repo fields are written when provided."""
    _write(
        tmp_path,
        """\
        # Active workspace

        projects: []
        """,
    )
    add_layer_entry(
        str(tmp_path),
        "gh",
        "/opt/gh",
        client="ghcorp",
        repo="https://github.com/example/repo.git",
    )
    content = _read(tmp_path)
    assert "client: ghcorp" in content
    assert "repo: https://github.com/example/repo.git" in content


def test_add_layer_duplicate_is_skipped(tmp_path, capsys):
    """Adding the same name twice leaves exactly one entry."""
    _write(
        tmp_path,
        """\
        mesh_layers:
        - name: acme
          path: /opt/acme
          client: acme

        projects: []
        """,
    )
    result = add_layer_entry(str(tmp_path), "acme", "/opt/acme", client="acme")
    assert result is False
    content = _read(tmp_path)
    assert content.count("- name: acme") == 1


def test_add_layer_appends_to_existing_section(tmp_path):
    """A second layer is appended inside the existing mesh_layers: block.

    Note: when `projects:` is written as a bare section key (no inline value),
    the boundary detector correctly places the new entry inside mesh_layers.
    With `projects: []` (inline value), the detector does not fire — the entry
    is still appended at the end of the file, which is the documented behaviour
    of the original add_mesh_layer._update_workspace logic.
    """
    _write(
        tmp_path,
        """\
        # Active workspace

        mesh_layers:
        - name: first
          path: /opt/first
          client: first

        projects:
        - name: alpha
          path: /opt/alpha
          added: 2024-01-01T00:00:00
        """,
    )
    add_layer_entry(str(tmp_path), "second", "/opt/second", client="second")
    content = _read(tmp_path)
    assert "- name: first" in content
    assert "- name: second" in content
    # both must be above projects: (bare section key triggers boundary detection)
    assert content.index("- name: second") < content.index("projects:")


# ── remove_layer_entry ───────────────────────────────────────────────────────


def test_remove_layer_preserves_others(tmp_path):
    """Removing one layer keeps the sibling and the section header."""
    _write(
        tmp_path,
        """\
        mesh_layers:
        - name: alpha
          path: /opt/alpha
          client: alpha
        - name: beta
          path: /opt/beta
          client: beta

        projects: []
        """,
    )
    remove_layer_entry(str(tmp_path), "alpha")
    content = _read(tmp_path)
    assert "- name: alpha" not in content
    assert "- name: beta" in content
    assert "mesh_layers:" in content


def test_remove_layer_strips_blank_continuations(tmp_path):
    """BUG-01 regression for layers: blank lines inside entry are removed."""
    _write(
        tmp_path,
        """\
        mesh_layers:
        - name: alpha
          path: /opt/alpha
          client: alpha

          added: 2024-01-01
        - name: beta
          path: /opt/beta
          client: beta

        projects: []
        """,
    )
    remove_layer_entry(str(tmp_path), "alpha")
    content = _read(tmp_path)
    assert "- name: alpha" not in content
    assert "  added: 2024-01-01" not in content
    assert "- name: beta" in content
    assert "client: beta" in content


def test_remove_layer_nonexistent_is_idempotent(tmp_path):
    """Removing a name that is not present leaves the file unchanged."""
    original = "mesh_layers:\n- name: beta\n  path: /opt/beta\n  client: beta\n"
    _wf(tmp_path).write_text(original)
    remove_layer_entry(str(tmp_path), "ghost")
    assert _read(tmp_path) == original


# ── set_mcp_source ───────────────────────────────────────────────────────────


def test_set_mcp_source_creates_block(tmp_path):
    """When no mcp_source: exists, the block is inserted above projects:."""
    _write(
        tmp_path,
        """\
        # Active workspace

        projects:
        - name: alpha
          path: /opt/alpha
        """,
    )
    set_mcp_source(str(tmp_path), "/opt/mcp")
    content = _read(tmp_path)
    assert "mcp_source:" in content
    assert "path: /opt/mcp" in content
    assert content.index("mcp_source:") < content.index("projects:")
    assert "- name: alpha" in content


def test_set_mcp_source_replaces_existing(tmp_path):
    """An existing mcp_source block is fully replaced; no duplicate path lines."""
    _write(
        tmp_path,
        """\
        # Active workspace

        mcp_source:
          path: /opt/old-mcp
          repo: https://example.com/old.git

        projects: []
        """,
    )
    set_mcp_source(str(tmp_path), "/opt/new-mcp")
    content = _read(tmp_path)
    assert "path: /opt/new-mcp" in content
    assert "path: /opt/old-mcp" not in content
    assert content.count("mcp_source:") == 1
    assert content.count("path:") == 1


def test_set_mcp_source_with_repo(tmp_path):
    """repo= field is written when provided."""
    _write(
        tmp_path,
        """\
        projects: []
        """,
    )
    set_mcp_source(str(tmp_path), "/opt/mcp", repo="https://github.com/x/y.git")
    content = _read(tmp_path)
    assert "repo: https://github.com/x/y.git" in content


# ── unset_mcp_source ─────────────────────────────────────────────────────────


def test_unset_mcp_source_strips_block(tmp_path):
    """The mcp_source: block and its body are fully removed."""
    _write(
        tmp_path,
        """\
        # Active workspace

        mcp_source:
          path: /opt/mcp

        projects: []
        """,
    )
    unset_mcp_source(str(tmp_path))
    content = _read(tmp_path)
    assert "mcp_source:" not in content
    assert "path: /opt/mcp" not in content
    assert "projects:" in content


def test_unset_mcp_source_idempotent(tmp_path):
    """Calling unset when no mcp_source exists does not crash."""
    original = "# Active workspace\n\nprojects: []\n"
    _wf(tmp_path).write_text(original)
    unset_mcp_source(str(tmp_path))
    content = _read(tmp_path)
    assert "mcp_source:" not in content
    assert "projects:" in content


def test_unset_mcp_source_preserves_surrounding_sections(tmp_path):
    """mesh_layers and projects are untouched after stripping mcp_source."""
    _write(
        tmp_path,
        """\
        mesh_layers:
        - name: acme
          path: /opt/acme
          client: acme

        mcp_source:
          path: /opt/mcp

        projects:
        - name: alpha
          path: /opt/alpha
        """,
    )
    unset_mcp_source(str(tmp_path))
    content = _read(tmp_path)
    assert "mcp_source:" not in content
    assert "mesh_layers:" in content
    assert "- name: acme" in content
    assert "- name: alpha" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
