# QA Report — Windows native, Developer Mode ON (`feat/windows-python-migration`)

**Date:** 2026-06-12
**Platform:** Windows 11 Pro (10.0.26200) — native (no WSL2)
**Python:** 3.13.2 (`python`, miniconda; pytest 9.0.3)
**git:** 2.47.1.windows.2
**Developer Mode:** ON (`AllowDevelopmentWithoutDevLicense = 0x1`) — symlink privilege confirmed
**bash available:** Git Bash / MSYS2 (used for the parity block)
**HEAD:** `a3cd60a` — fix: cross-platform robustness fixes 2 & 3 (Windows no-symlink privilege)

This run validates the migration with symlink privilege available, so no tests
are skipped for lack of privilege. It is the companion to the earlier
Developer-Mode-OFF report (`qa-report-windows-python-migration.md`).

---

## Summary

| Block | Result | Notes |
|-------|--------|-------|
| 0 Clone | **PASS** | SHA `a3cd60a` |
| 1 pytest | **PASS** | 148 passed, 0 skipped, 0 failed |
| 2 init | **PASS** | fresh clone: real symlinks + all files created |
| 3 parity bash↔Python | **PASS** | Python path fully functional; generated text files byte-identical |
| 4 E2E smoke | **FAIL** | `remove_mesh_layer` of last layer returns exit 3 (empty `mesh_layers:` marker) |
| 5 security hooks | **PASS** | 4/4 cases as expected |
| 6 drift detection | **FAIL** | sync/fix-drift exit 3 (same marker); check-only exit 0 (wrong test subject) |
| 7 Windows native | **PASS** | py.cmd OK, junction survives sync, UTF-8 roundtrip identical |

**Overall: 6/8 PASS** (blocks 0, 1, 2, 3, 5, 7)

> The two FAILs (blocks 4 and 6) were diagnosed to a single root cause — a bare
> empty `mesh_layers:` marker left by `remove_layer_entry`, which `sync_symlinks`
> reports as a degraded workspace (exit 3). Fixed in branch
> `fix/remove-layer-empty-marker` (PR #2). See the "Diagnosis" section below.

---

## Block 0 — Fresh clone

```
git clone <repo> <TEMP>/maicelium-qa
git checkout feat/windows-python-migration
git log --oneline -1
```
```
a3cd60a fix: cross-platform robustness fixes 2 & 3 (Windows no-symlink privilege)
```
**PASS**

## Block 1 — Automated test suite

```
pytest tests/ -v
```
```
============================ 148 passed in 40.83s =============================
```
**PASS** — 148 passed, 0 skipped, 0 failed.

## Block 2 — Fresh init (Python only)

`python bin/init.py` on a clean clone → exit 0. All targets created as **real symlinks**:

| Target | symlinks |
|--------|----------|
| `.cursor/rules` | 6 |
| `.cursor/skills-cursor` | 14 |
| `.agents/rules` | 6 |
| `.agents/skills` | 9 |

Files present: `WORKSPACE.md`, `mAIcelium.code-workspace`, `.claude/projects-context.md`, `.claude/settings.json`. `chat-style.mdc` → `islink=True`.

**PASS**

> Note: running init on a `Copy-Item` copy of an already-initialised clone fails with
> `WinError 183` (target already exists) — a copy artifact, not an init defect. A
> genuinely fresh clone initialises cleanly.

## Block 3 — Bash ↔ Python parity (Git Bash)

| Path | init | sync |
|------|------|------|
| bash (`init.sh` / `sync_symlinks.sh`) | exit 0 | **exit 1** (`ln: ...workspace-guide/workspace-guide: No such file or directory`) |
| Python (`init.py` / `sync_symlinks.py`) | exit 0 | exit 0 (43 symlinks, `.mcp.json` created) |

- `diff mAIcelium.code-workspace` → **empty (identical)**
- `diff .claude/projects-context.md` → **empty (identical)**
- Symlink / `.mcp.json` diffs are non-empty only because the **bash path failed** to create symlinks (Git Bash peculiarity — informative per spec). The Python path is the migration target and works fully.

**PASS** (Python path)

## Block 4 — E2E lifecycle smoke (Python only)

| Command | exit |
|---------|------|
| `add_project demo --code-only` | 0 (symlinks `projects/demo`, `.cursor/rules/demo--r.md` created) |
| `add_mesh_layer acme --client demo` | 0 |
| `add_mcp_source` | 0 |
| `set_project_flag demo context_inline false` | 0 |
| `sync_symlinks.py` / `--dry-run` / `--check-only` | 0 / 0 / 0 |
| `remove_mcp_source` | 0 |
| **`remove_mesh_layer acme`** | **3** + `WORKSPACE.md parser returned empty for section 'mesh_layers'` warning |
| `remove_project demo` | 0 |

Symlink create/remove lifecycle verified (created with `islink=True`, removed with `lexists=False`).

**FAIL** — `remove_mesh_layer` of the last layer returns exit 3. See Diagnosis.

## Block 5 — Security hooks

| Input | Expected | Actual |
|-------|----------|--------|
| `rm -rf /` | block | block |
| `terraform apply` | block | block |
| `ls -la` | allow | allow |
| `file_path: C:\Windows\System32\drivers\etc\hosts` (outside workspace) | block | block |

**PASS** (4/4)

## Block 6 — Drift detection

| Command | exit |
|---------|------|
| `sync_symlinks.py --check-only` | 0 |
| `sync_symlinks.py` | 3 |
| `sync_symlinks.py --fix-drift` | 3 |

The `exit 3` is the same empty-marker degraded state inherited from Block 4. `check-only`
returned 0 because the drift was introduced on a **global rule** (`global.mdc`), which is not
drift-tracked — drift detection applies to **layer reflections** only. Re-tested on a layer
reflection: `check-only` → exit 1 with `drift [identical]`, `fix-drift` reconverts to symlink.

**FAIL** — see Diagnosis.

## Block 7 — Windows native

- `bin\py.cmd bin\sync_symlinks.py` → exit 0
- **Junction** (`mklink /J`) survives `sync_symlinks.py` (still a junction, target reachable) — not destroyed
- **UTF-8 roundtrip** (ñ / accents): file content read back **identical** via Python

**PASS**

---

## Diagnosis (blocks 4 & 6)

Both FAILs share one root cause, confirmed in code and empirically.

Removing the **last** mesh layer leaves a bare `mesh_layers:` marker in `WORKSPACE.md`.
`sync_symlinks.py` treats a present-but-empty section marker as a *degraded* workspace and
returns **exit 3** (`bin/sync_symlinks.py:880-915`); `load_workspace_section` warns about it
(`bin/_lib/workspace.py:190-198`). `remove_mesh_layer` propagates the sync exit code
(`bin/remove_mesh_layer.py:192-194`), so a successful removal reports failure.

Empirical confirmation — same "zero layers" state, only the marker format differs:

| WORKSPACE.md | exit | warnings |
|---|---|---|
| `mesh_layers:` (bare, empty) | **3** | 2 |
| no marker line | 0 | 0 |
| `mesh_layers: []` (inline) | 0 | 0 |

The `check-only` exit 0 in Block 6 is **by design** (global rules use `ln -sfn` semantics and
are not drift-tracked), not a defect.

**Fix:** `remove_layer_entry` now drops the empty section marker (mirroring `unset_mcp_source`),
in branch `fix/remove-layer-empty-marker` / PR #2. The validator is left unchanged (its
degraded-state detection is asserted by `test_sync_workspace_md_warning_on_empty_section_marker`
and still guards hand-malformed sections). After the fix, `remove_mesh_layer` of the last layer
exits 0 with no warnings; test suite 148 → 150.

---

## Environment

| Item | Value |
|------|-------|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.2 (miniconda) |
| pytest | 9.0.3 |
| git | 2.47.1.windows.2 |
| Developer Mode | ON |
| bash | Git Bash / MSYS2 |

**6/8 blocks PASS** (0, 1, 2, 3, 5, 7); blocks 4 & 6 fixed in PR #2.
