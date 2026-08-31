"""Tests for bin/add_mesh_layer.py and bin/set_project_flag.py.

Scripts are invoked as subprocesses with MAICELIUM_ROOT pointing at a temp
workspace, so the WORKSPACE.md mutations are exercised end-to-end (parse +
write + sync/context regeneration). Each test asserts the on-disk state of
WORKSPACE.md after the command runs.
"""
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")

from _marks import requires_symlink  # noqa: E402


def _bootstrap_workspace(tmp_path):
    """Create a minimal workspace skeleton: bin/, mesh/conventions.json, projects/, mesh/rules/."""
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


def _make_fake_layer(base, name="fake-layer", with_rules=True, with_skills=True):
    """Create a fake mesh-layer repo with optional rules/skills directories."""
    layer = base / name
    layer.mkdir()
    if with_rules:
        (layer / "rules").mkdir()
        (layer / "rules" / "demo.mdc").write_text("---\nalwaysApply: true\n---\n# demo\n")
    if with_skills:
        (layer / "skills").mkdir()
        skill = layer / "skills" / "demo-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: demo-skill\n---\n# body\n")
    return layer


def _run(script_name, *args, cwd):
    """Invoke a script in bin/ as a subprocess against MAICELIUM_ROOT=cwd."""
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
# add_mesh_layer
# ────────────────────────────────────────────────────────────────────────────


@requires_symlink
def test_add_layer_to_empty_workspace(tmp_path):
    """No WORKSPACE.md exists; the script creates one with the layer registered."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "acme")

    result = _run("add_mesh_layer.py", "acme", str(layer), "--client", "acme", cwd=ws)

    assert result.returncode == 0, result.stderr + result.stdout

    wf = ws / "WORKSPACE.md"
    assert wf.is_file()
    content = wf.read_text()
    assert "mesh_layers:" in content
    assert "- name: acme" in content
    assert f"path: {os.path.realpath(str(layer))}" in content
    assert "client: acme" in content


@requires_symlink
def test_add_layer_reversed_order_path_first(tmp_path):
    """Either-order: <path> <name> works the same as the classic <name> <path>."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "acme")

    result = _run("add_mesh_layer.py", str(layer), "acme", cwd=ws)  # path first

    assert result.returncode == 0, result.stderr + result.stdout
    content = (ws / "WORKSPACE.md").read_text()
    assert "- name: acme" in content
    assert f"path: {os.path.realpath(str(layer))}" in content


@requires_symlink
def test_add_layer_explicit_flags(tmp_path):
    """--path/--name resolve roles unambiguously."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "acme")

    result = _run("add_mesh_layer.py", "--path", str(layer), "--name", "acme", cwd=ws)

    assert result.returncode == 0, result.stderr + result.stdout
    content = (ws / "WORKSPACE.md").read_text()
    assert "- name: acme" in content
    assert f"path: {os.path.realpath(str(layer))}" in content


def test_add_layer_ambiguous_two_existing_dirs_errors(tmp_path):
    """Both args are bare existing directories -> hard error forcing --path/--name."""
    ws = _bootstrap_workspace(tmp_path)
    (ws / "aaa").mkdir()
    (ws / "bbb").mkdir()

    result = _run("add_mesh_layer.py", "aaa", "bbb", cwd=ws)

    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "mbiguous" in out
    assert "--path" in out and "--name" in out


@requires_symlink
def test_add_layer_appends_to_existing_section(tmp_path):
    """An existing mesh_layers: section gains a second entry without losing the first."""
    ws = _bootstrap_workspace(tmp_path)
    layer1 = _make_fake_layer(tmp_path, "first")
    layer2 = _make_fake_layer(tmp_path, "second")

    wf = ws / "WORKSPACE.md"
    # Use a populated projects: list so the section-boundary detector
    # (which only fires on lines that strictly end with ':') recognises
    # projects: as the next top-level key.
    wf.write_text(
        textwrap.dedent(
            f"""\
            # Active workspace

            mesh_layers:
            - name: first
              path: {os.path.realpath(str(layer1))}
              client: first

            projects:
            - name: alpha
              path: /opt/alpha
              added: 2024-01-01T00:00:00
            """
        )
    )

    result = _run("add_mesh_layer.py", "second", str(layer2), "--client", "second", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "- name: first" in content
    assert "- name: second" in content
    # second entry must live inside the mesh_layers: block (i.e. above projects:)
    assert content.index("- name: second") < content.index("projects:")
    # alpha (project) is still present and below projects:
    assert content.index("- name: alpha") > content.index("projects:")


@requires_symlink
def test_add_layer_with_repo_url_with_colons(tmp_path):
    """Repo URLs containing ':' (e.g. https://...) are preserved as a single value."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "ghlayer")

    url = "https://github.com/example/repo.git"
    result = _run(
        "add_mesh_layer.py", "ghlayer", str(layer),
        "--client", "example",
        "--repo", url,
        cwd=ws,
    )

    assert result.returncode == 0, result.stderr + result.stdout

    content = (ws / "WORKSPACE.md").read_text()
    assert f"repo: {url}" in content


@requires_symlink
def test_add_layer_duplicate_warns_and_skips(tmp_path):
    """Adding the same name twice keeps a single entry and reports a warning."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "dup")

    r1 = _run("add_mesh_layer.py", "dup", str(layer), "--client", "dup", cwd=ws)
    assert r1.returncode == 0, r1.stderr + r1.stdout

    r2 = _run("add_mesh_layer.py", "dup", str(layer), "--client", "dup", cwd=ws)
    assert r2.returncode == 0, r2.stderr + r2.stdout
    assert "already exists" in r2.stdout.lower()

    content = (ws / "WORKSPACE.md").read_text()
    # exactly one "- name: dup" line
    assert content.count("- name: dup") == 1


@requires_symlink
def test_add_layer_preserves_projects_section(tmp_path):
    """WORKSPACE.md with an existing projects: list keeps it intact after a layer is added."""
    ws = _bootstrap_workspace(tmp_path)
    layer = _make_fake_layer(tmp_path, "newlayer")

    wf = ws / "WORKSPACE.md"
    wf.write_text(
        textwrap.dedent(
            """\
            # Active workspace

            projects:
            - name: alpha
              path: /opt/alpha
              added: 2024-01-01T00:00:00
            - name: beta
              path: /opt/beta
              added: 2024-01-02T00:00:00
            """
        )
    )

    result = _run(
        "add_mesh_layer.py", "newlayer", str(layer),
        "--client", "newcli",
        cwd=ws,
    )
    assert result.returncode == 0, result.stderr + result.stdout

    content = wf.read_text()
    assert "- name: alpha" in content
    assert "path: /opt/alpha" in content
    assert "- name: beta" in content
    assert "mesh_layers:" in content
    assert "- name: newlayer" in content
    # layer block must appear above projects: block
    assert content.index("mesh_layers:") < content.index("projects:")
    # the layer entry sits inside the mesh_layers block, not after projects:
    assert content.index("- name: newlayer") < content.index("projects:")


# ────────────────────────────────────────────────────────────────────────────
# set_project_flag
# ────────────────────────────────────────────────────────────────────────────


def _seed_workspace_with_project(ws, project="demo", path="/opt/demo", extra_flag=None):
    """Write a WORKSPACE.md containing a single project entry."""
    wf = ws / "WORKSPACE.md"
    lines = ["# Active workspace", "", "projects:", f"- name: {project}", f"  path: {path}",
             "  added: 2024-01-01T00:00:00"]
    if extra_flag is not None:
        k, v = extra_flag
        lines.append(f"  {k}: {v}")
    wf.write_text("\n".join(lines) + "\n")
    return wf


def test_set_flag_inserts_new(tmp_path):
    """An entry without the flag gains a new line for it."""
    ws = _bootstrap_workspace(tmp_path)
    wf = _seed_workspace_with_project(ws)

    result = _run("set_project_flag.py", "demo", "context_inline", "false", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "added" in result.stdout

    content = wf.read_text()
    assert "context_inline: false" in content
    # flag sits below the project entry, before any next top-level key
    assert content.index("- name: demo") < content.index("context_inline: false")


def test_set_flag_updates_existing(tmp_path):
    """An entry with the flag present has it rewritten in-place (no duplicate)."""
    ws = _bootstrap_workspace(tmp_path)
    wf = _seed_workspace_with_project(ws, extra_flag=("context_inline", "true"))

    result = _run("set_project_flag.py", "demo", "context_inline", "false", cwd=ws)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "updated" in result.stdout

    content = wf.read_text()
    assert content.count("context_inline:") == 1
    assert "context_inline: false" in content
    assert "context_inline: true" not in content


def test_set_flag_nonexistent_project_errors(tmp_path):
    """Unknown project name => non-zero exit with a clear error."""
    ws = _bootstrap_workspace(tmp_path)
    _seed_workspace_with_project(ws)

    result = _run("set_project_flag.py", "ghost", "context_inline", "false", cwd=ws)
    assert result.returncode != 0
    msg = (result.stderr + result.stdout).lower()
    assert "ghost" in msg
    assert "not found" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
