"""Tests for bin/_lib/context.py — regenerators for workspace files."""
import json
import os

from _lib.context import regenerate_claude_context, regenerate_workspace_file
from _marks import requires_symlink


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ────────────────────────────────────────────────────────────────────────────
# regenerate_workspace_file
# ────────────────────────────────────────────────────────────────────────────


def test_regenerate_workspace_file_no_projects(tmp_path):
    root = str(tmp_path)
    regenerate_workspace_file(root)
    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    assert os.path.isfile(wsfile)
    with open(wsfile, encoding="utf-8") as f:
        data = json.load(f)
    assert data == {
        "folders": [{"path": ".", "name": "mAIcelium"}],
        "settings": {},
    }
    # Verify indent=2 is preserved (look at raw text)
    with open(wsfile, encoding="utf-8") as f:
        raw = f.read()
    assert '  "folders"' in raw
    assert raw.endswith("\n")


def test_regenerate_workspace_file_preserves_settings(tmp_path):
    root = str(tmp_path)
    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    with open(wsfile, "w", encoding="utf-8") as f:
        json.dump(
            {"folders": [{"path": "stale", "name": "old"}], "settings": {"theme": "dark"}},
            f,
        )
    regenerate_workspace_file(root)
    with open(wsfile, encoding="utf-8") as f:
        data = json.load(f)
    # Stale folders replaced, settings preserved
    assert data["folders"] == [{"path": ".", "name": "mAIcelium"}]
    assert data["settings"] == {"theme": "dark"}


@requires_symlink
def test_regenerate_workspace_file_with_projects(tmp_path):
    root = str(tmp_path)
    real_repo = tmp_path / "real_repo"
    real_repo.mkdir()
    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(real_repo), str(projects / "foo"))

    regenerate_workspace_file(root)
    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    with open(wsfile, encoding="utf-8") as f:
        data = json.load(f)
    names = [f["name"] for f in data["folders"]]
    assert "mAIcelium" in names
    assert "foo" in names
    foo_entry = next(f for f in data["folders"] if f["name"] == "foo")
    assert foo_entry["path"] == os.path.realpath(str(real_repo))


def test_regenerate_workspace_file_corrupted_existing_resets(tmp_path):
    """If existing file is unreadable JSON, regenerate as fresh."""
    root = str(tmp_path)
    wsfile = os.path.join(root, "mAIcelium.code-workspace")
    with open(wsfile, "w", encoding="utf-8") as f:
        f.write("{ not valid json")
    regenerate_workspace_file(root)
    with open(wsfile, encoding="utf-8") as f:
        data = json.load(f)
    assert data["folders"] == [{"path": ".", "name": "mAIcelium"}]
    assert data["settings"] == {}


# ────────────────────────────────────────────────────────────────────────────
# regenerate_claude_context
# ────────────────────────────────────────────────────────────────────────────


def test_regenerate_claude_context_empty_workspace(tmp_path):
    root = str(tmp_path)
    regenerate_claude_context(root)
    outfile = os.path.join(root, ".claude", "projects-context.md")
    assert os.path.isfile(outfile)
    content = open(outfile, encoding="utf-8").read()
    assert "# mAIcelium Agent Context" in content
    assert "## Workspace Rules" in content
    assert "## Active Projects" in content
    assert "_No active projects._" in content


def test_regenerate_claude_context_with_mesh_rule(tmp_path):
    root = str(tmp_path)
    _write(
        os.path.join(root, "mesh", "rules", "test.mdc"),
        "---\ndescription: A test rule\n---\n\n# Test Rule body\nThis is the body.\n",
    )
    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "### test" in content
    assert "# Test Rule body" in content
    assert "This is the body." in content
    # Frontmatter must NOT appear
    assert "description: A test rule" not in content


def test_regenerate_claude_context_strips_yaml_frontmatter(tmp_path):
    root = str(tmp_path)
    _write(
        os.path.join(root, "mesh", "rules", "alpha.mdc"),
        "---\nkey: val\n---\nactual content\n",
    )
    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "actual content" in content
    assert "key: val" not in content
    # The literal closing delim of frontmatter must be stripped too
    rules_section_start = content.index("### alpha")
    rules_section = content[rules_section_start:]
    assert "---" not in rules_section.split("##", 1)[0]


def test_regenerate_claude_context_rule_without_frontmatter(tmp_path):
    """A rule file without a leading frontmatter is emitted verbatim."""
    root = str(tmp_path)
    _write(
        os.path.join(root, "mesh", "rules", "plain.mdc"),
        "# Plain rule\nNo frontmatter here.\n",
    )
    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "# Plain rule" in content
    assert "No frontmatter here." in content


def test_regenerate_claude_context_multiple_rules_sorted(tmp_path):
    root = str(tmp_path)
    _write(os.path.join(root, "mesh", "rules", "zebra.mdc"), "zebra body\n")
    _write(os.path.join(root, "mesh", "rules", "alpha.mdc"), "alpha body\n")
    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert content.index("### alpha") < content.index("### zebra")


@requires_symlink
def test_regenerate_claude_context_project_with_rules_and_skills(tmp_path):
    """A project symlink whose target has rules and skills must be inlined."""
    root = str(tmp_path)
    # Real repo with .cursor/rules/*.md and .cursor/skills/<name>/SKILL.md
    repo = tmp_path / "myrepo"
    repo.mkdir()
    _write(str(repo / ".cursor" / "rules" / "r1.md"), "---\nfoo: bar\n---\nrule one body\n")
    _write(str(repo / ".cursor" / "skills" / "s1" / "SKILL.md"), "skill one body\n")
    _write(str(repo / ".cursor" / "plans" / "p.md"), "plan\n")

    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(repo), str(projects / "myproj"))

    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "### myproj" in content
    assert "#### Rules" in content
    assert "##### r1.md" in content
    assert "rule one body" in content
    assert "foo: bar" not in content  # frontmatter stripped
    assert "#### Skills" in content
    assert "##### s1" in content
    assert "skill one body" in content
    assert "#### Project Data (accessible via symlink)" in content
    assert "`projects/myproj/.cursor/plans/`" in content


@requires_symlink
def test_regenerate_claude_context_no_inline_project(tmp_path):
    """A project listed with context_inline:false gets a placeholder line only."""
    root = str(tmp_path)
    _write(
        os.path.join(root, "WORKSPACE.md"),
        "projects:\n"
        "  - name: framework\n"
        "    path: /abs/framework\n"
        "    context_inline: false\n",
    )
    repo = tmp_path / "framework_repo"
    repo.mkdir()
    _write(str(repo / ".cursor" / "rules" / "r.md"), "should not appear\n")
    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(repo), str(projects / "framework"))

    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "### framework" in content
    assert "Framework repo" in content
    assert "should not appear" not in content


@requires_symlink
def test_regenerate_claude_context_project_no_rules_no_skills(tmp_path):
    """If a project has no rules and no skills, emit the empty marker."""
    root = str(tmp_path)
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(repo), str(projects / "empty"))

    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "### empty" in content
    assert "_No rules or skills found for this project._" in content


@requires_symlink
def test_regenerate_claude_context_layer_rules(tmp_path):
    """A mesh layer whose client matches the project name contributes rules."""
    root = str(tmp_path)
    layer = tmp_path / "client_layer"
    layer.mkdir()
    _write(str(layer / "rules" / "layer-rule.md"), "layer rule body\n")
    _write(str(layer / "skills" / "layer-skill" / "SKILL.md"), "layer skill body\n")

    _write(
        os.path.join(root, "WORKSPACE.md"),
        "mesh_layers:\n"
        f"  - name: client_layer\n"
        f"    path: {layer}\n"
        f"    client: clientproj\n",
    )

    repo = tmp_path / "client_repo"
    repo.mkdir()
    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(repo), str(projects / "clientproj"))

    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()
    assert "### clientproj" in content
    assert "##### layer-rule.md" in content
    assert "layer rule body" in content
    assert "##### layer-skill" in content
    assert "layer skill body" in content


@requires_symlink
def test_no_inline_avoids_duplicate_layer_content(tmp_path):
    """A project with context_inline:false must not have its body inlined twice.

    This is the dedup regression test for KI-001: when a project is also
    covered by a mesh layer, flagging it context_inline:false prevents the
    layer content from appearing twice in the generated file.
    """
    root = str(tmp_path)

    # Build a large unique body that would be easy to spot if duplicated
    unique_marker = "UNIQUE_LAYER_CONTENT_XK7Q2P"
    large_body = "\n".join([f"# Layer rule line {i}: {unique_marker}" for i in range(200)])

    # Create a mesh layer with this body
    layer = tmp_path / "client_layer_dedup"
    layer.mkdir()
    _write(str(layer / "rules" / "layer-rule.md"), large_body + "\n")

    # WORKSPACE.md: project is flagged context_inline:false and has a layer
    _write(
        os.path.join(root, "WORKSPACE.md"),
        "projects:\n"
        "  - name: bigproj\n"
        "    path: /abs/bigproj\n"
        "    context_inline: false\n"
        "mesh_layers:\n"
        f"  - name: client_layer_dedup\n"
        f"    path: {layer}\n"
        f"    client: bigproj\n",
    )

    # Create a real repo symlink so the project is discovered
    repo = tmp_path / "bigproj_repo"
    repo.mkdir()
    projects = tmp_path / "projects"
    projects.mkdir()
    os.symlink(str(repo), str(projects / "bigproj"))

    regenerate_claude_context(root)
    content = open(os.path.join(root, ".claude", "projects-context.md"), encoding="utf-8").read()

    # Project heading must appear
    assert "### bigproj" in content

    # The no-inline placeholder must appear
    assert "Framework repo" in content

    # The large layer body must NOT be inlined (context_inline:false suppresses it)
    assert unique_marker not in content, (
        "Layer content must not be inlined when context_inline:false is set — "
        "this prevents duplication when a project is also covered by a mesh layer"
    )
