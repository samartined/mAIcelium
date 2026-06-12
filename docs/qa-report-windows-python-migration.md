# QA Report — Windows Python Migration (`feat/windows-python-migration`)

**Date:** 2026-06-12  
**Platform:** Windows 11 Pro (10.0.26200) — native (no WSL2)  
**Python:** 3.13.14  
**pytest:** 9.0.3 (installed via `python3 -m pip install pytest`)  
**git:** 2.47.1.windows.2  
**Developer Mode:** OFF  
**HEAD:** `21bb14b` — refactor: consolidate WORKSPACE.md mutations in _lib/workspace_writer (ARCH-01)

---

## Summary

| Block | Result | Notes |
|-------|--------|-------|
| 0 Clone | **PASS** | SHA `21bb14b` |
| 1 pytest | **FAIL** | 97 passed / 50 failed |
| 2 init | **FAIL** | 3 files not created |
| 3 parity bash↔Python | **FAIL** | bash sync exit=1; Python init exit=1; all diffs exit=2 |
| 4 E2E smoke | **FAIL** | symlink ops blocked; `--check-only` exit=2 |
| 5 security hooks | **PASS** | 9/9 cases as expected |
| 6 drift detection | **FAIL** | all subcommands exit=2 |
| 7 Windows native | **FAIL** | symlinks not created (Dev Mode OFF, expected); WORKSPACE.md roundtrip DIFFERENT |

**Overall: 2/8 PASS** (blocks 0, 5)

---

## Block 0 — Fresh clone

```
git clone https://github.com/samartined/mAIcelium <TEMP_DIR>/maicelium-qa
cd <TEMP_DIR>/maicelium-qa
git checkout feat/windows-python-migration
git log --oneline -1
```

```
21bb14b refactor: consolidate WORKSPACE.md mutations in _lib/workspace_writer (ARCH-01)
```

**Result: PASS**

---

## Block 1 — Automated test suite

```
pytest tests/ -v
```

```
======================= 50 failed, 97 passed in 12.20s ==========================
```

**Result: FAIL — 97 passed / 50 failed (expected 147/147)**

### Failed tests

```
tests/test_add_remove_project.py::test_add_project_creates_symlinks_and_workspace_entry
tests/test_add_remove_project.py::test_add_project_refuses_duplicate
tests/test_add_remove_project.py::test_add_project_code_only_skips_imports
tests/test_add_remove_project.py::test_add_then_remove_leaves_clean_state
tests/test_add_remove_project.py::test_remove_preserves_other_sections
tests/test_add_remove_project.py::test_remove_cleans_agents_projects_tree
tests/test_add_remove_project.py::test_remove_project_preserves_following_entry_with_blank_line
tests/test_context.py::test_regenerate_workspace_file_with_projects
tests/test_context.py::test_regenerate_claude_context_project_with_rules_and_skills
tests/test_context.py::test_regenerate_claude_context_no_inline_project
tests/test_context.py::test_regenerate_claude_context_project_no_rules_no_skills
tests/test_context.py::test_regenerate_claude_context_layer_rules
tests/test_hooks.py::test_guard_write_allows_layer_symlink
tests/test_init.py::test_init_creates_directory_tree
tests/test_init.py::test_init_creates_gitkeep_files
tests/test_init.py::test_init_idempotent
tests/test_init.py::test_init_preserves_existing_settings
tests/test_init.py::test_init_creates_workspace_file
tests/test_init.py::test_init_preserves_existing_workspace_md
tests/test_init.py::test_init_creates_claude_context
tests/test_init.py::test_init_writes_python_hooks_in_settings
tests/test_init.py::test_init_includes_python_permissions
tests/test_init.py::test_init_runs_sync_at_end
tests/test_layer_flag.py::test_add_layer_to_empty_workspace
tests/test_layer_flag.py::test_add_layer_appends_to_existing_section
tests/test_layer_flag.py::test_add_layer_with_repo_url_with_colons
tests/test_layer_flag.py::test_add_layer_duplicate_warns_and_skips
tests/test_layer_flag.py::test_add_layer_preserves_projects_section
tests/test_mcp_and_remove_layer.py::test_remove_mesh_layer_existing
tests/test_mcp_and_remove_layer.py::test_add_mcp_source_creates_section
tests/test_mcp_and_remove_layer.py::test_add_mcp_source_replaces_existing
tests/test_mcp_and_remove_layer.py::test_remove_mcp_source_strips_section
tests/test_mcp_and_remove_layer.py::test_remove_mcp_source_no_section_idempotent
tests/test_mcp_and_remove_layer.py::test_remove_mesh_layer_preserves_following_entry_with_blank_line
tests/test_platform.py::test_create_link_creates_symlink
tests/test_platform.py::test_create_link_replaces_existing
tests/test_platform.py::test_create_link_idempotent
tests/test_symlinks.py::test_find_broken_symlinks_detects_dangling
tests/test_symlinks.py::test_find_broken_symlinks_ignores_valid
tests/test_symlinks.py::test_find_broken_symlinks_respects_maxdepth
tests/test_symlinks.py::test_detect_junction_false_on_linux
tests/test_sync.py::test_sync_empty_workspace
tests/test_sync.py::test_sync_creates_rule_symlinks
tests/test_sync.py::test_sync_dry_run_no_changes
tests/test_sync.py::test_sync_check_only_no_drift_returns_0
tests/test_sync.py::test_sync_drift_detection_identical
tests/test_sync.py::test_sync_drift_detection_divergent
tests/test_sync.py::test_sync_relative_symlinks
tests/test_sync.py::test_sync_clean_broken_symlinks
tests/test_sync.py::test_sync_workspace_md_warning_on_empty_section_marker
```

### Representative traceback (symlink-related failures)

```
bin\_lib\platform.py:98: OSError

OSError: [WinError 1314] The client does not have a required privilege:
  '<relative_source>' -> '<TEMP_DIR>\...\<link_target>'

The above exception was the direct cause of the following exception:

PermissionError: Failed to create symlink at '<TEMP_DIR>\...'.
In Windows, this requires 'Developer Mode' to be enabled.
Enable it: Settings -> System -> For developers -> Developer Mode.
After enabling it, you may need to restart your terminal.

bin\_lib\platform.py:103: PermissionError
```

---

## Block 2 — Fresh init (Python only)

```
python3 bin/init.py
```

```
Initializing mAIcelium at: <REPO_ROOT>
  -> Creating Cursor symlinks...
PermissionError: Failed to create symlink at '<REPO_ROOT>\.cursor\rules\chat-style.mdc'.
In Windows, this requires 'Developer Mode' to be enabled.
[exit=1]
```

### Filesystem state after aborted init

| Item | Status |
|------|--------|
| `mesh/skills/_common/` | PRESENT |
| `mesh/skills/_domains/` | PRESENT |
| `mesh/layers/` | PRESENT |
| `.cursor/rules/` | PRESENT |
| `.cursor/skills-cursor/` | PRESENT |
| `.agents/` | PRESENT |
| `.claude/` | PRESENT |
| `.claude/settings.json` | PRESENT |
| `WORKSPACE.md` | **ABSENT** |
| `mAIcelium.code-workspace` | **ABSENT** |
| `.claude/projects-context.md` | **ABSENT** |

### `.claude/settings.json` contains

| Entry | Present |
|-------|---------|
| `bin/py.sh bin/sync_symlinks.py` | YES |
| `guard_bash.py` | YES |
| `guard_write.py` | YES |

**Result: FAIL** (3 expected files absent due to init abort on symlink error)

---

## Block 3 — Bash ↔ Python parity

> **Note:** `bash` available is Git Bash / MSYS2 (not WSL2). Tests executed via Bash tool.

```
# Clone 1 (bash path)
git clone <URL> <TEMP_DIR>/qa-bash && cd <TEMP_DIR>/qa-bash && git checkout feat/windows-python-migration
bash bin/init.sh && bash bin/sync_symlinks.sh

# Clone 2 (python path)
git clone <URL> <TEMP_DIR>/qa-py && cd <TEMP_DIR>/qa-py && git checkout feat/windows-python-migration
python3 bin/init.py && python3 bin/sync_symlinks.py
```

### bash path

```
bash bin/init.sh  → exit=0  (all steps OK)
bash bin/sync_symlinks.sh →
  ln: failed to create symbolic link '.cursor/skills-cursor/workspace-guide/workspace-guide': No such file or directory
  exit=1
```

### python path

```
python3 bin/init.py →
  PermissionError: Failed to create symlink (WinError 1314, Developer Mode OFF)
  exit=1

python3 bin/sync_symlinks.py →
  Cannot create symbolic links. Enable Developer Mode on Windows.
  exit=2
```

### Diffs

All diff commands returned **exit=2** (file not found) — no output files were generated by the Python path.

```
diff .mcp.json            → exit=2 (file missing on both sides)
diff .cursor/mcp.json     → exit=2 (file missing on both sides)
diff .agents/mcp.json     → exit=2 (file missing on both sides)
diff mAIcelium.code-workspace → exit=2 (missing on Python side)
diff WORKSPACE.md         → exit=2 (missing on Python side)
diff .claude/projects-context.md → exit=2 (missing on Python side)
```

Symlink diffs: **no data** (no symlinks created by either path under these conditions).

**Result: FAIL**

---

## Block 4 — E2E lifecycle smoke (Python only)

```
python3 bin/add_project.py demo <TEMP_DIR>/qa-proj --code-only
```
```
PermissionError: Failed to create symlink at '<REPO_ROOT>\projects\demo'.
exit=1
```

```
python3 bin/add_mesh_layer.py acme <TEMP_DIR>/qa-layer --client demo
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
Warning: '<TEMP_DIR>/qa-layer' has no rules/ or skills/ directory.
  WORKSPACE.md updated
Mesh layer 'acme' added -> <TEMP_DIR>\qa-layer (client: demo)
  Running sync...
exit=2
```

```
python3 bin/add_mcp_source.py <TEMP_DIR>/qa-mcp
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
  WORKSPACE.md updated (mcp_source: <TEMP_DIR>\qa-mcp)
MCP source registered -> <TEMP_DIR>\qa-mcp
  Running sync...
exit=2
```

```
python3 bin/set_project_flag.py demo context_inline false
```
```
Error: project 'demo' not found in WORKSPACE.md
exit=1
```

### `cat WORKSPACE.md` — first checkpoint

```yaml
# Active workspace

mesh_layers:
- name: acme
  path: <TEMP_DIR>\qa-layer
  client: demo

projects: []

mcp_source:
  path: <TEMP_DIR>\qa-mcp
```

```
python3 bin/sync_symlinks.py          → exit=2  (Cannot create symbolic links)
python3 bin/sync_symlinks.py --dry-run → exit=2  (Cannot create symbolic links)
python3 bin/sync_symlinks.py --check-only → exit=2
```

```
python3 bin/remove_mcp_source.py
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
Removing MCP source ...
  WORKSPACE.md updated
  Running sync to regenerate IDE configs...
exit=2
```

```
python3 bin/remove_mesh_layer.py acme
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
Removing layer 'acme' ...
  WORKSPACE.md updated
Layer 'acme' removed from workspace
exit=2
```

```
python3 bin/remove_project.py demo
```
```
Project 'demo' does not exist in the workspace.
exit=1
```

### `cat WORKSPACE.md` — second checkpoint

```yaml
# Active workspace

mesh_layers:

projects: []
```

**`--check-only` exit code: 2**

**Result: FAIL**

---

## Block 5 — Security hooks

| # | Input | Expected | Actual | Result |
|---|-------|----------|--------|--------|
| 1 | `rm -rf /` | block | `{"decision":"block","reason":"Blocked: rm -rf on root/home directory..."}` | **PASS** |
| 2 | `git push --force origin main` | block | `{"decision":"block","reason":"Blocked: force push to main/master..."}` | **PASS** |
| 3 | `terraform apply` | block | `{"decision":"block","reason":"Blocked: Terraform command requires tfswitch preflight..."}` | **PASS** |
| 4 | `ls -la` | allow | *(empty stdout, exit=0)* | **PASS** |
| 5 | `tfswitch && terraform apply` | allow | *(empty stdout, exit=0)* | **PASS** |
| 6 | `file_path: /etc/passwd` | block | `{"decision":"block","reason":"Blocked: file_path '/etc/passwd' is outside the workspace..."}` | **PASS** |
| 7 | `file_path: <ROOT>/.env` | block | `{"decision":"block","reason":"Protected file: .env..."}` | **PASS** |
| 8 | `file_path: <ROOT>/.claude/settings.json` | block | `{"decision":"block","reason":"Protected file: .claude/settings.json..."}` | **PASS** |
| 9 | `file_path: <ROOT>/mesh/rules/test.mdc` | allow | *(empty stdout, exit=0)* | **PASS** |

**Result: PASS (9/9)**

---

## Block 6 — Drift detection

```
python3 bin/sync_symlinks.py --check-only
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
exit=2
```

```
python3 bin/sync_symlinks.py
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
exit=2
```

```
python3 bin/sync_symlinks.py --fix-drift
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
exit=2
```

**Result: FAIL** — all subcommands exit=2; no drift data available.

---

## Block 7 — Windows native

```
bin\py.cmd bin\sync_symlinks.py
```
```
Cannot create symbolic links. Enable Developer Mode on Windows.
exit=0
```

- Symlinks created: **NO** (Developer Mode OFF — expected behavior per spec)

### WORKSPACE.md roundtrip with accented characters (PowerShell write → PowerShell read)

```
Result: DIFFERENT
```

- Written bytes end with `0A` (LF)
- Read-back bytes end with `0D 0A` (CRLF)

PowerShell `Set-Content` adds a trailing `\r\n` on read-back. Python reads the file correctly as UTF-8.

**Result: FAIL**
- Symlink failure with Developer Mode OFF: expected per spec
- WORKSPACE.md roundtrip CRLF issue: unexpected (PS write→read adds trailing `\r\n`)

---

## Environment

| Item | Value |
|------|-------|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.14 |
| pytest | 9.0.3 |
| git | 2.47.1.windows.2 |
| Developer Mode | OFF |
| bash available | Git Bash / MSYS2 (not WSL2) |

**2/8 blocks PASS** (block 0, block 5)
