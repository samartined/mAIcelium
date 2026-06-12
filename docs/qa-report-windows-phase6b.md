# QA Report — Windows native, Phase 6b HEAD (Developer Mode ON)

**Date:** 2026-06-12
**Platform:** Windows 11 Pro (10.0.26200) — native
**Python:** 3.13.2 (`python`, miniconda; pytest 9.0.3)
**git:** 2.47.1.windows.2
**Developer Mode:** ON (`AllowDevelopmentWithoutDevLicense = 0x1`)
**HEAD:** `3a19c8f` — Merge pull request #3 from samartined/chore/phase-6b-remove-bash

Raw test-execution run. No diagnosis. Paths anonymized (`<TEMP>`, `<repo>`).

---

## Summary

| Block | Result | Notes |
|-------|--------|-------|
| 0 HEAD | **PASS** | SHA `3a19c8f` |
| 1 pytest | **FAIL** | 151 passed, 1 failed (`test_guard_write_allows_claude_plans_dir`) |
| 2 no bash | **PASS** | `bin\*.sh` = only `py.sh`; `bin\hooks\*.sh` = none |
| 3 init | **PASS** | exit 0; real symlinks; `bash perms: []` |
| 4 E2E | **PASS** | `remove_mesh_layer` of last layer = exit 0, 0 warnings, marker dropped |
| 5 drift | **PASS** | check-only exit 1 `[identical]`; fix-drift reconverts |
| 6 hooks | **PASS** | 5/5 as expected |
| 7 shim | **PASS** | `py.cmd sync` exit 0 |

**7/8 blocks PASS** (0, 2, 3, 4, 5, 6, 7). Block 1 FAIL.

---

## Block 0 — Final HEAD

```
git checkout feat/windows-python-migration && git pull
git log --oneline -1
```
```
3a19c8f Merge pull request #3 from samartined/chore/phase-6b-remove-bash
```
Recent history:
```
3a19c8f Merge pull request #3 from samartined/chore/phase-6b-remove-bash
81c186e chore: retire bash dual-track, Python is now the sole script surface (Phase 6b)
778f57b fix(guard-write): allow ~/.claude/plans/ in outside-workspace guard
7f0d27a fix(workspace): drop empty mesh_layers marker on last layer removal
a01ef0d docs: add Windows native QA report (Developer Mode ON)
```
**PASS**

## Block 1 — Full test suite

```
pytest tests/ -v
```
```
======================= 1 failed, 151 passed in 47.10s ========================
```
**FAIL** — expected 152 passed / 0 skipped / 0 failed. 0 skipped, 1 failed.

### Failed test (raw traceback)

```
FAILED tests/test_hooks.py::test_guard_write_allows_claude_plans_dir

    def test_guard_write_allows_claude_plans_dir(tmp_path):
        """Claude Code's own plan dir (~/.claude/plans/) is outside the workspace
        but legitimate harness state -- it must be allowed, not blocked."""
        home = tmp_path / "home"
        plans = home / ".claude" / "plans"
        plans.mkdir(parents=True)
        target = plans / "some-plan.md"
        result = _run_hook(
            GUARD_WRITE,
            {"tool_input": {"file_path": str(target)}},
            env={"MAICELIUM_ROOT": str(tmp_path / "workspace"), "HOME": str(home)},
        )
        assert result.returncode == 0
>       assert result.stdout.strip() == ""
E       assert '{"decision":...ty measure."}' == ''
E
E         + {"decision": "block", "reason": "Blocked: file_path '<TEMP>\\<pytest-tmp>\\home\\.claude\\plans\\some-plan.md' is outside the workspace. Refusing write as a safety measure."}

tests\test_hooks.py:306: AssertionError
```

## Block 2 — No bash remaining

```
> Get-ChildItem bin\*.sh
py.sh
> Get-ChildItem bin\hooks\*.sh
(none)
> Get-ChildItem bin\hooks
guard_bash.py
guard_write.py
```
**PASS**

## Block 3 — Real init with symlinks

`python bin\init.py` on a fresh clone → exit 0.
```
islink global.mdc: True
bash perms: []
WORKSPACE.md: True | code-workspace: True | projects-context: True
```
**PASS**

> Note: running init on a `Copy-Item` copy of the main clone (after it had run
> pytest) fails with `WinError 183` (target already exists) — a copy artifact.
> A genuinely fresh clone (`.cursor` absent before init) initialises cleanly (exit 0).

## Block 4 — E2E lifecycle (Python only)

| Command | exit |
|---------|------|
| `add_project demo --code-only` | 0 |
| `add_mesh_layer acme --client demo` | 0 |
| `set_project_flag demo context_inline false` | 0 |
| `sync_symlinks.py` | 0 |
| `sync_symlinks.py --dry-run` | 0 |
| `sync_symlinks.py --check-only` | 0 |
| **`remove_mesh_layer acme`** | **0** (0 warnings) |
| `remove_project demo` | 0 |

`type WORKSPACE.md` (after adds):
```
# Active workspace

created: <ts>

mesh_layers:
- name: acme
  path: <TEMP>\layer
  client: demo

projects:
- name: demo
  path: <TEMP>\p
  added: <ts>
  context_inline: false
```

`type WORKSPACE.md` (after removes):
```
# Active workspace

created: <ts>

projects:
```

`mesh_layers:` marker present after removal: **0 occurrences** (dropped).

**PASS** — `remove_mesh_layer` of the last layer exits 0 with no warnings and the marker is gone.

## Block 5 — Drift detection (layer reflection)

Reflection `mesh/skills/_common/foo` (symlink) replaced with an identical real dir.

```
sync_symlinks.py --check-only  → "drift: <repo>\mesh\skills\_common\foo [identical]"   exit=1
sync_symlinks.py               → "Layer-managed drift detected: 1 reflection(s) ...
                                   - [identical] <repo>\mesh\skills\_common\foo
                                   -> 1 identical reflection(s) can be auto-converted: re-run with --fix-drift"   exit=0
sync_symlinks.py --fix-drift   → "Symlinks synced."   exit=0   (reflection back to symlink: True)
```
**PASS**

## Block 6 — Hooks

| Input | Expected | Actual |
|-------|----------|--------|
| `rm -rf /` | block | block |
| `terraform apply` | block | block |
| `ls -la` | allow | allow (empty stdout, exit 0) |
| `file_path: C:\Windows\System32\drivers\etc\hosts` | block | block |
| `file_path: <USERPROFILE>\.claude\plans\x.md` | allow | allow (empty stdout, exit 0) |

**PASS** (5/5)

## Block 7 — Windows shim

```
bin\py.cmd bin\sync_symlinks.py
  Syncing symlinks...
  ...
  Symlinks synced.
exit=0
```
**PASS**

---

## Environment

| Item | Value |
|------|-------|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.2 (miniconda) |
| pytest | 9.0.3 |
| git | 2.47.1.windows.2 |
| Developer Mode | ON |

**Python 3.13.2 — Developer Mode ON confirmed — 7/8 blocks PASS.**

Non-green:
- Block 1 — `tests/test_hooks.py::test_guard_write_allows_claude_plans_dir` (traceback above).
