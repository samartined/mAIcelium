"""Tests for bin/init.py — Python port of bin/init.sh.

Each test builds a minimal workspace under tmp_path and exercises a single
behavior of the initializer: directory tree, .gitkeep files, idempotence,
settings-preservation, workspace file generation.
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import init  # noqa: E402


# ── Test 1: directory tree ──────────────────────────────────────────────────


def test_init_creates_directory_tree(tmp_path):
    """After init, every expected directory must exist under root."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    expected = [
        "mesh/skills/_common/code-review",
        "mesh/skills/_common/debug",
        "mesh/skills/_common/documentation",
        "mesh/skills/_common/git-workflow",
        "mesh/skills/_common/planning",
        "mesh/skills/_common/refactoring",
        "mesh/skills/_common/security-review",
        "mesh/skills/_common/testing",
        "mesh/skills/_common/workspace-guide",
        "mesh/skills/_clients",
        "mesh/skills/_domains/frontend-react",
        "mesh/skills/_domains/backend-python",
        "mesh/skills/_domains/devops",
        "mesh/skills/_domains/obsidian",
        "mesh/skills/_domains/cursor",
        "mesh/layers",
        "mesh/rules",
        "mesh/prompts",
        "mesh/commands",
        ".cursor/rules",
        ".cursor/skills-cursor",
        ".claude/commands",
        ".agents",
        ".agents/rules",
        ".agents/skills",
        ".agents/workflows",
        "projects",
        "repos",
        "bin",
    ]
    for rel in expected:
        full = tmp_path / rel
        assert full.is_dir(), f"missing directory: {rel}"


# ── Test 2: .gitkeep files ──────────────────────────────────────────────────


def test_init_creates_gitkeep_files(tmp_path):
    """projects/, mesh/skills/_clients/, and mesh/layers/ get .gitkeep files."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    assert (tmp_path / "projects" / ".gitkeep").is_file()
    assert (tmp_path / "mesh" / "skills" / "_clients" / ".gitkeep").is_file()
    assert (tmp_path / "mesh" / "layers" / ".gitkeep").is_file()


# ── Test 3: idempotence ─────────────────────────────────────────────────────


def test_init_idempotent(tmp_path):
    """Calling init twice in a row must succeed and not change state on the second run."""
    rc1 = init.main(root=str(tmp_path))
    assert rc1 == 0

    rc2 = init.main(root=str(tmp_path))
    assert rc2 == 0

    # Spot-check key artifacts still exist after the second run.
    assert (tmp_path / "WORKSPACE.md").is_file()
    assert (tmp_path / "mAIcelium.code-workspace").is_file()
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / "projects" / ".gitkeep").is_file()


# ── Test 4: preserve manual edits to .claude/settings.json ──────────────────


def test_init_preserves_existing_settings(tmp_path):
    """Pre-created .claude/settings.json must not be overwritten by init."""
    # Pre-create settings.json with custom content
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    settings_file = settings_dir / "settings.json"
    custom = {"permissions": {"allow": ["Custom(thing:*)"]}, "model": "opus"}
    settings_file.write_text(json.dumps(custom))

    rc = init.main(root=str(tmp_path))
    assert rc == 0

    on_disk = json.loads(settings_file.read_text())
    assert on_disk == custom, "init must not overwrite an existing settings.json"


# ── Test 5: workspace file is generated ─────────────────────────────────────


def test_init_creates_workspace_file(tmp_path):
    """mAIcelium.code-workspace must exist after init and contain a folders list."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    ws_file = tmp_path / "mAIcelium.code-workspace"
    assert ws_file.is_file()

    data = json.loads(ws_file.read_text())
    assert "folders" in data
    # At minimum, the root folder entry must be present.
    assert any(
        f.get("name") == "mAIcelium" and f.get("path") == "."
        for f in data["folders"]
    )


# ── Test 6: WORKSPACE.md preserved when present ─────────────────────────────


def test_init_preserves_existing_workspace_md(tmp_path):
    """Pre-existing WORKSPACE.md must not be overwritten."""
    wf = tmp_path / "WORKSPACE.md"
    custom_content = "# My custom workspace\n\nprojects:\n  - name: foo\n    path: /bar\n"
    wf.write_text(custom_content)

    rc = init.main(root=str(tmp_path))
    assert rc == 0
    assert wf.read_text() == custom_content


# ── Test 7: claude project context is generated ─────────────────────────────


def test_init_creates_claude_context(tmp_path):
    """init must produce .claude/projects-context.md."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    ctx = tmp_path / ".claude" / "projects-context.md"
    assert ctx.is_file()
    content = ctx.read_text()
    assert "AUTO-GENERATED" in content
    assert "# mAIcelium Agent Context" in content
