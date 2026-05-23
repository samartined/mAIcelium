"""Tests for bin/remove_mesh_layer.py, bin/add_mcp_source.py and bin/remove_mcp_source.py.

Scripts are invoked as subprocesses with MAICELIUM_ROOT pointing at a temp
workspace. Each test asserts the on-disk state of WORKSPACE.md after the
command runs.
"""
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")


def _bootstrap_workspace(tmp_path):
    """Create a minimal workspace skeleton with conventions + mesh/ dirs."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "projects").mkdir()
    (ws / "mesh").mkdir()
    (ws / "mesh" / "rules").mkdir()
    (ws / "mesh" / "skills").mkdir()
    (ws / "mesh" / "commands").mkdir()
    shutil.copy(
        os.path.join(_REPO_ROOT, "mesh", "conventions.json"),
        str(ws / "mesh" / "conventions.json"),
    )
    return ws


def _run(script_name, *args, cwd):
    """Invoke a script in bin/ as a subprocess with MAICELIUM_ROOT=cwd."""
    script = os.path.join(_BIN_DIR, script_name)
    env = {**os.environ, "MAICELIUM_ROOT": str(cwd)}
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


# ────────────────────────────────────────────────────────────────────────────
# remove_mesh_layer
# ────────────────────────────────────────────────────────────────────────────


def test_remove_mesh_layer_existing(tmp_path):
    """Removing one layer from a two-layer section keeps the other intact."""
    ws = _bootstrap_workspace(tmp_path)

    layer_a = tmp_path / "layer-a"
    layer_a.mkdir()
    layer_b = tmp_path / "layer-b"
    layer_b.mkdir()

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            f"""\
            # Active workspace

            mesh_layers:
            - name: alpha
              path: {layer_a}
              client: alpha
            - name: beta
              path: {layer_b}
              client: beta

            projects: []
            """
        )
    )

    result = _run("remove_mesh_layer.py", "alpha", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "- name: alpha" not in content
    assert "- name: beta" in content
    assert f"path: {layer_b}" in content
    assert "client: beta" in content
    # mesh_layers: section is still present
    assert "mesh_layers:" in content


def test_remove_mesh_layer_nonexistent_warns(tmp_path):
    """Removing a missing layer does NOT crash: exit 0, warning emitted."""
    ws = _bootstrap_workspace(tmp_path)

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            """\
            # Active workspace

            projects: []
            """
        )
    )

    result = _run("remove_mesh_layer.py", "ghost", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    out = (result.stdout + result.stderr).lower()
    assert "ghost" in out
    assert "not found" in out


# ────────────────────────────────────────────────────────────────────────────
# add_mcp_source
# ────────────────────────────────────────────────────────────────────────────


def test_add_mcp_source_creates_section(tmp_path):
    """No prior mcp_source: section -> a new block is inserted.

    Note: when `projects:` lives on its own line (no inline value), the script
    inserts mcp_source BEFORE it (parity-with-bash). With `projects: []`
    inline, the boundary detector does not fire and the block is appended.
    """
    ws = _bootstrap_workspace(tmp_path)

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            """\
            # Active workspace

            projects:
            - name: alpha
              path: /opt/alpha
            """
        )
    )

    mcp_dir = tmp_path / "fake-mcp"
    mcp_dir.mkdir()

    result = _run("add_mcp_source.py", str(mcp_dir), cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "mcp_source:" in content
    assert f"path: {os.path.realpath(str(mcp_dir))}" in content
    # mcp_source must sit above projects: (block-form parses as section boundary)
    assert content.index("mcp_source:") < content.index("projects:")
    # the existing project entry is preserved
    assert "- name: alpha" in content


def test_add_mcp_source_replaces_existing(tmp_path):
    """An existing mcp_source: block is replaced (no duplicate path lines)."""
    ws = _bootstrap_workspace(tmp_path)

    old_mcp = tmp_path / "old-mcp"
    old_mcp.mkdir()
    new_mcp = tmp_path / "new-mcp"
    new_mcp.mkdir()

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            f"""\
            # Active workspace

            mcp_source:
              path: {old_mcp}
              repo: https://example.com/old.git

            projects: []
            """
        )
    )

    result = _run("add_mcp_source.py", str(new_mcp), cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    new_real = os.path.realpath(str(new_mcp))
    assert f"path: {new_real}" in content
    assert f"path: {old_mcp}" not in content
    # exactly one mcp_source: line
    assert content.count("mcp_source:") == 1
    assert content.count("path:") == 1


# ────────────────────────────────────────────────────────────────────────────
# remove_mcp_source
# ────────────────────────────────────────────────────────────────────────────


def test_remove_mcp_source_strips_section(tmp_path):
    """When mcp_source: is present, remove deletes the whole block."""
    ws = _bootstrap_workspace(tmp_path)

    mcp_dir = tmp_path / "fake-mcp"
    mcp_dir.mkdir()

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            f"""\
            # Active workspace

            mcp_source:
              path: {mcp_dir}

            projects: []
            """
        )
    )

    result = _run("remove_mcp_source.py", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "mcp_source:" not in content
    assert f"path: {mcp_dir}" not in content
    # projects: section is still present
    assert "projects:" in content


def test_remove_mcp_source_no_section_idempotent(tmp_path):
    """Removing when no section exists does not crash; file stays valid."""
    ws = _bootstrap_workspace(tmp_path)

    wf = ws / "WORKSPACE.md"
    original = textwrap.dedent(
        """\
        # Active workspace

        projects: []
        """
    )
    wf.write_text(original)

    result = _run("remove_mcp_source.py", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    out = (result.stdout + result.stderr).lower()
    assert "no mcp source" in out or "not registered" in out

    content = wf.read_text()
    assert "projects:" in content
    assert "mcp_source:" not in content


# ────────────────────────────────────────────────────────────────────────────
# BUG-01 regression for remove_mesh_layer: blank lines inside entry block
# ────────────────────────────────────────────────────────────────────────────


def test_remove_mesh_layer_preserves_following_entry_with_blank_line(tmp_path):
    """Removing 'alpha' layer must not leave orphaned indented lines from its block.

    A blank line sits inside the alpha layer entry (between 'path:' and
    'added:').  After removal only the beta entry must remain; the orphaned
    '  added: 2024-01-01' line must not survive.
    """
    ws = _bootstrap_workspace(tmp_path)

    layer_a = tmp_path / "layer-a"
    layer_a.mkdir()
    layer_b = tmp_path / "layer-b"
    layer_b.mkdir()

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        "# Active workspace\n"
        "\n"
        "mesh_layers:\n"
        "- name: alpha\n"
        f"  path: {layer_a}\n"
        "  client: alpha\n"
        "\n"
        "  added: 2024-01-01\n"
        "- name: beta\n"
        f"  path: {layer_b}\n"
        "  client: beta\n"
        "\n"
        "projects: []\n"
    )

    result = _run("remove_mesh_layer.py", "alpha", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "- name: alpha" not in content
    # Orphan line that was previously left behind by the bug.
    assert "  added: 2024-01-01" not in content
    # Beta entry must be fully intact.
    assert "- name: beta" in content
    assert f"path: {layer_b}" in content
    assert "client: beta" in content
    # Section header must survive.
    assert "mesh_layers:" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
