"""Tests for bin/init.py — Python port of bin/init.sh.

Each test builds a minimal workspace under tmp_path and exercises a single
behavior of the initializer: directory tree, .gitkeep files, idempotence,
settings-preservation, workspace file generation.

Coverage note (TR-5 honesty):
init's symlink-dependent happy path is unprovable on Windows-without-Dev-Mode
(init aborts early, returning exit 2 without privilege). Coverage on that
platform consists of:
  (a) the abort branch — see tests/test_init_privilege.py;
  (b) the symlink-free sub-path — see test_init_directory_tree_without_symlink_privilege
      below (calls helpers directly, avoids init.main so no privilege check fires).
"""
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR = os.path.join(_REPO_ROOT, "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import init  # noqa: E402

from _marks import requires_symlink


# ── Autouse fixture: isolate HOME/XDG so init never writes to the real HOME ──


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """Redirect HOME and XDG_CONFIG_HOME into a throwaway dir for every test.

    This prevents _create_smug_symlink from writing to the developer's real
    ~/.config/smug/ directory (TR-3 isolation). MAICELIUM_CONFIG_HOME is the
    authoritative override used by init._smug_config_home().
    """
    fake = tmp_path / "_home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))           # POSIX expanduser
    monkeypatch.setenv("USERPROFILE", str(fake))    # Windows expanduser
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake / ".config"))
    monkeypatch.setenv("MAICELIUM_CONFIG_HOME", str(fake / ".config"))


# ── Test 1: directory tree ──────────────────────────────────────────────────


@requires_symlink
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


@requires_symlink
def test_init_creates_gitkeep_files(tmp_path):
    """projects/, mesh/skills/_clients/, and mesh/layers/ get .gitkeep files."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    assert (tmp_path / "projects" / ".gitkeep").is_file()
    assert (tmp_path / "mesh" / "skills" / "_clients" / ".gitkeep").is_file()
    assert (tmp_path / "mesh" / "layers" / ".gitkeep").is_file()


# ── Test 3: idempotence ─────────────────────────────────────────────────────


@requires_symlink
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


@requires_symlink
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


@requires_symlink
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


@requires_symlink
def test_init_preserves_existing_workspace_md(tmp_path):
    """Pre-existing WORKSPACE.md must not be overwritten."""
    wf = tmp_path / "WORKSPACE.md"
    custom_content = "# My custom workspace\n\nprojects:\n  - name: foo\n    path: /bar\n"
    wf.write_text(custom_content)

    rc = init.main(root=str(tmp_path))
    assert rc == 0
    assert wf.read_text() == custom_content


# ── Test 7: claude project context is generated ─────────────────────────────


@requires_symlink
def test_init_creates_claude_context(tmp_path):
    """init must produce .claude/projects-context.md."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    ctx = tmp_path / ".claude" / "projects-context.md"
    assert ctx.is_file()
    content = ctx.read_text()
    assert "AUTO-GENERATED" in content
    assert "# mAIcelium Agent Context" in content


# ── Test 8: settings.json contains Python hooks ─────────────────────────────


@requires_symlink
def test_init_writes_python_hooks_in_settings(tmp_path):
    """After init, .claude/settings.json must include all three Python hook commands."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    settings_file = tmp_path / ".claude" / "settings.json"
    content = settings_file.read_text()
    assert "bin/py.sh bin/sync_symlinks.py" in content
    assert "bin/py.sh bin/hooks/guard_bash.py" in content
    assert "bin/py.sh bin/hooks/guard_write.py" in content


# ── Test 9: settings.json contains Python permissions ───────────────────────


@requires_symlink
def test_init_includes_python_permissions(tmp_path):
    """After init, .claude/settings.json must include Python-specific permissions."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    settings_file = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings_file.read_text())
    allowed = data["permissions"]["allow"]
    assert "Bash(python3:bin/*)" in allowed
    assert "Bash(bin/py.sh:*)" in allowed


# ── Test 10: init runs sync at the end ──────────────────────────────────────


@requires_symlink
def test_init_runs_sync_at_end(tmp_path):
    """After init, mAIcelium.code-workspace must exist (produced by sync_symlinks)."""
    rc = init.main(root=str(tmp_path))
    assert rc == 0

    ws_file = tmp_path / "mAIcelium.code-workspace"
    assert ws_file.is_file(), "sync_symlinks must have run and produced the workspace file"


# ── Test 11: TR-3 — nothing written outside root ────────────────────────────


@requires_symlink
def test_init_creates_nothing_outside_root(tmp_path_factory, monkeypatch):
    """init must not write anything under HOME when MAICELIUM_CONFIG_HOME redirects smug.

    Uses two DISJOINT temp dirs: one for the workspace root, one for the
    fake HOME. This ensures "outside root" is genuinely distinct from root.
    The autouse fixture already sets HOME/XDG/MAICELIUM_CONFIG_HOME; this test
    OVERRIDES those vars to point at a separate disjoint home, and redirects
    MAICELIUM_CONFIG_HOME back into root so the smug link stays inside root.
    """
    root = tmp_path_factory.mktemp("workspace")
    disjoint_home = tmp_path_factory.mktemp("home")

    # Override the autouse fixture's env: disjoint_home is the "real" HOME,
    # MAICELIUM_CONFIG_HOME points inside root so smug link lands there.
    monkeypatch.setenv("HOME", str(disjoint_home))
    monkeypatch.setenv("USERPROFILE", str(disjoint_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(disjoint_home / ".config"))
    monkeypatch.setenv("MAICELIUM_CONFIG_HOME", str(root / ".config"))

    # Snapshot every path under disjoint_home BEFORE init.
    def _snapshot(base):
        result = set()
        for dirpath, dirnames, filenames in os.walk(str(base)):
            for name in filenames + dirnames:
                result.add(os.path.join(dirpath, name))
        return result

    before = _snapshot(disjoint_home)

    rc = init.main(root=str(root))
    assert rc == 0

    after = _snapshot(disjoint_home)

    # Nothing new should have appeared under disjoint_home.
    new_paths = after - before
    assert new_paths == set(), (
        f"init wrote {len(new_paths)} path(s) outside root into HOME:\n"
        + "\n".join(sorted(new_paths))
    )

    # The smug symlink, if created, must live inside root — not under disjoint_home.
    smug_link = root / ".config" / "smug" / "mAIcelium.yml"
    if smug_link.exists() or smug_link.is_symlink():
        assert str(smug_link).startswith(str(root)), (
            f"smug symlink landed outside root: {smug_link}"
        )
    # Verify it did NOT land inside disjoint_home.
    bad_link = disjoint_home / ".config" / "smug" / "mAIcelium.yml"
    assert not (bad_link.exists() or bad_link.is_symlink()), (
        f"smug symlink incorrectly written to disjoint HOME: {bad_link}"
    )


# ── Test 12: TR-5 — symlink-free directory tree (no privilege required) ─────


def test_init_directory_tree_without_symlink_privilege(tmp_path, monkeypatch):
    """Verify the symlink-free helpers produce the expected tree and .gitkeep files.

    This test calls _create_directory_tree and the seed writers DIRECTLY,
    bypassing init.main (which would abort on Windows without Developer Mode).
    MAICELIUM_FORCE_NO_SYMLINK=1 documents the intent but is not strictly
    needed here because the helpers don't check privilege themselves.
    Nothing should be written outside tmp_path/root.
    """
    monkeypatch.setenv("MAICELIUM_FORCE_NO_SYMLINK", "1")
    root = tmp_path / "workspace"
    root.mkdir()

    # Call the symlink-free helpers directly.
    init._create_directory_tree(str(root))
    init._create_settings_json(str(root))
    init._create_workspace_md(str(root))

    # The canonical directory tree must be in place.
    expected_dirs = [
        "mesh/skills/_common/code-review",
        "mesh/skills/_common/testing",
        "mesh/skills/_domains/frontend-react",
        "mesh/layers",
        "mesh/rules",
        "mesh/prompts",
        "mesh/commands",
        ".cursor/rules",
        ".cursor/skills-cursor",
        ".claude/commands",
        ".agents",
        "projects",
        "repos",
        "bin",
    ]
    for rel in expected_dirs:
        assert (root / rel).is_dir(), f"missing directory after symlink-free init: {rel}"

    # .gitkeep sentinels must exist.
    assert (root / "projects" / ".gitkeep").is_file()
    assert (root / "mesh" / "layers" / ".gitkeep").is_file()
    assert (root / "mesh" / "skills" / "_clients" / ".gitkeep").is_file()

    # settings.json must have been dropped.
    settings = root / ".claude" / "settings.json"
    assert settings.is_file(), ".claude/settings.json must exist after symlink-free init"
    data = json.loads(settings.read_text())
    assert "permissions" in data

    # Nothing was written outside root.
    root_str = str(root)
    home_str = str(tmp_path / "_home")  # from autouse fixture
    if os.path.isdir(home_str):
        for dirpath, _, filenames in os.walk(home_str):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                assert full.startswith(root_str) or not full.startswith(home_str), (
                    f"unexpected write outside root: {full}"
                )
