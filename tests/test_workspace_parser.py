"""Tests for bin/_lib/workspace.py — unified WORKSPACE.md parser.

These tests are the golden replacement for the 3 ad-hoc parsers in bin/_lib.sh.
Each canonical case must produce the same result as the bash heredocs would.
"""
import os

import pytest

from _lib.workspace import _parse_path_value, load_workspace_section


def write(root, name, content):
    """Helper: write a file at root/name."""
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ────────────────────────────────────────────────────────────────────────────
# Canonical (well-formed) fixtures
# ────────────────────────────────────────────────────────────────────────────


def test_no_workspace_md_returns_empty(tmp_path):
    root = str(tmp_path)
    assert load_workspace_section(root, "mesh_layers") == []
    assert load_workspace_section(root, "mcp_source") is None
    assert load_workspace_section(root, "no_inline_projects") == []


def test_mesh_layers_single_layer(tmp_path):
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mesh_layers:\n"
        "  - name: acme\n"
        "    path: ~/code/acme-layer\n"
        "    client: acme\n"
        "    repo: https://github.com/acme/layer.git\n",
    )
    layers = load_workspace_section(root, "mesh_layers")
    assert len(layers) == 1
    assert layers[0]["name"] == "acme"
    assert layers[0]["client"] == "acme"
    assert layers[0]["path"] == os.path.normpath(os.path.expanduser("~/code/acme-layer"))
    assert layers[0]["repo"] == "https://github.com/acme/layer.git"


def test_mesh_layers_multiple(tmp_path):
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mesh_layers:\n"
        "  - name: foo\n"
        "    path: /abs/foo\n"
        "  - name: bar\n"
        "    path: relative/bar\n"
        "    client: bar\n",
    )
    layers = load_workspace_section(root, "mesh_layers")
    assert len(layers) == 2
    assert [l["name"] for l in layers] == ["foo", "bar"]
    assert layers[1]["path"] == os.path.normpath(os.path.join(root, "relative/bar"))


def test_mesh_layers_url_with_colons(tmp_path):
    """A `repo:` value with `https://...` must NOT confuse the parser."""
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mesh_layers:\n"
        "  - name: tricky\n"
        "    path: /tmp/tricky\n"
        "    repo: https://gitlab.com/group/sub/repo.git\n",
    )
    layers = load_workspace_section(root, "mesh_layers")
    assert layers[0]["repo"] == "https://gitlab.com/group/sub/repo.git"


def test_mcp_source_present(tmp_path):
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mcp_source:\n"
        "  path: ~/code/mcp-defs\n"
        "  repo: git@github.com:org/mcp.git\n",
    )
    src = load_workspace_section(root, "mcp_source")
    assert src is not None
    assert src["path"] == os.path.normpath(os.path.expanduser("~/code/mcp-defs"))
    assert src["repo"] == "git@github.com:org/mcp.git"


def test_mcp_source_no_path_returns_none(tmp_path):
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mcp_source:\n  repo: git@github.com:org/mcp.git\n",
    )
    assert load_workspace_section(root, "mcp_source") is None


def test_no_inline_projects(tmp_path):
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "projects:\n"
        "  - name: framework-repo\n"
        "    path: /abs/framework\n"
        "    context_inline: false\n"
        "  - name: normal-repo\n"
        "    path: /abs/normal\n"
        "    context_inline: true\n"
        "  - name: default-repo\n"
        "    path: /abs/default\n",
    )
    result = load_workspace_section(root, "no_inline_projects")
    assert result == ["framework-repo"]


def test_section_boundary_stops_parsing(tmp_path):
    """Once a new top-level key starts, parser must STOP, not bleed across."""
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mesh_layers:\n"
        "  - name: legitimate\n"
        "    path: /abs/legit\n"
        "mcp_source:\n"
        "  path: /should/not/leak/into/layers\n",
    )
    layers = load_workspace_section(root, "mesh_layers")
    assert len(layers) == 1
    assert layers[0]["name"] == "legitimate"


def test_section_absent_returns_empty(tmp_path):
    """A WORKSPACE.md without the requested section must return empty."""
    root = str(tmp_path)
    write(root, "WORKSPACE.md", "projects:\n  - name: solo\n    path: /abs/solo\n")
    assert load_workspace_section(root, "mesh_layers", warn_on_empty=False) == []


# ────────────────────────────────────────────────────────────────────────────
# Malformed fixtures (do not crash; produce best-effort output)
# ────────────────────────────────────────────────────────────────────────────


def test_malformed_empty_file(tmp_path):
    root = str(tmp_path)
    write(root, "WORKSPACE.md", "")
    assert load_workspace_section(root, "mesh_layers") == []
    assert load_workspace_section(root, "mcp_source") is None


def test_malformed_only_comments(tmp_path):
    root = str(tmp_path)
    write(root, "WORKSPACE.md", "# this is just a comment\n# nothing here\n")
    assert load_workspace_section(root, "mesh_layers") == []


def test_malformed_tabs_instead_of_spaces(tmp_path):
    """Tabs at start of indent — parser should NOT crash; may yield empty."""
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "mesh_layers:\n\t- name: tabby\n\t  path: /abs/tabby\n",
    )
    # Lines starting with \t do NOT start with ' ', so the boundary detector
    # treats them as if they were top-level. Best-effort: no crash.
    layers = load_workspace_section(root, "mesh_layers", warn_on_empty=False)
    assert isinstance(layers, list)


def test_warn_on_empty_section_marker(tmp_path, capsys):
    """If marker present but parser empty, emit a stderr warning."""
    root = str(tmp_path)
    write(root, "WORKSPACE.md", "mesh_layers:\n\nprojects:\n  - name: x\n    path: /x\n")
    load_workspace_section(root, "mesh_layers", warn_on_empty=True)
    captured = capsys.readouterr()
    assert "parser returned empty" in captured.err


def test_no_warn_on_genuinely_absent_section(tmp_path, capsys):
    """If marker absent, no warning."""
    root = str(tmp_path)
    write(root, "WORKSPACE.md", "projects:\n  - name: x\n    path: /x\n")
    load_workspace_section(root, "mesh_layers", warn_on_empty=True)
    captured = capsys.readouterr()
    assert "parser returned empty" not in captured.err


def test_unknown_section_raises(tmp_path):
    root = str(tmp_path)
    with pytest.raises(ValueError, match="Unknown section"):
        load_workspace_section(root, "bogus_section")


def test_no_inline_no_duplicate_at_section_boundary(tmp_path):
    """The bash original duplicates the last entry when a boundary key follows.
    This Python port deduplicates — intentional deviation, documented in code."""
    root = str(tmp_path)
    write(
        root,
        "WORKSPACE.md",
        "projects:\n"
        "  - name: framework-repo\n"
        "    path: /abs/framework\n"
        "    context_inline: false\n"
        "mesh_layers:\n"
        "  - name: x\n"
        "    path: /x\n",
    )
    result = load_workspace_section(root, "no_inline_projects")
    assert result == ["framework-repo"], f"expected no duplicate, got {result}"


# ────────────────────────────────────────────────────────────────────────────
# Security: path traversal (BUG-06)
# ────────────────────────────────────────────────────────────────────────────


def test_path_traversal_rejected(tmp_path, capsys):
    """Relative paths that escape workspace root via '..' must be rejected.

    _parse_path_value must emit a stderr warning and return the raw unresolved
    string instead of resolving to a system path like /etc.
    """
    root = str(tmp_path)
    raw = "../../etc"
    result = _parse_path_value(raw, root)

    # Must return the unresolved raw string, NOT /etc or similar
    assert result == raw, f"expected unresolved '{raw}', got '{result}'"

    # Must emit a warning to stderr
    captured = capsys.readouterr()
    assert "escapes workspace root" in captured.err
    assert raw in captured.err


def test_path_traversal_absolute_allowed(tmp_path):
    """Absolute paths must not trigger the traversal guard (they are explicit).

    _parse_path_value calls os.path.normpath, which on Windows converts forward
    slashes to backslashes. Normalize the expectation accordingly so this test
    holds cross-platform.
    """
    root = str(tmp_path)
    result = _parse_path_value("/usr/local/share/data", root)
    assert result == os.path.normpath("/usr/local/share/data")


def test_path_within_root_allowed(tmp_path):
    """Relative paths that stay within root must resolve normally."""
    root = str(tmp_path)
    result = _parse_path_value("subdir/file.txt", root)
    assert result == os.path.normpath(os.path.join(root, "subdir/file.txt"))


def test_path_traversal_no_escape_allowed(tmp_path):
    """'../sibling' that resolves outside root must also be rejected."""
    root = str(tmp_path / "workspace")
    raw = "../outside"
    result = _parse_path_value(raw, root)
    assert result == raw
