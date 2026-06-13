# Roadmap / Backlog

Tracked follow-up work after the bash → Python migration (Phases 1–6b, completed
2026-06-12). Items here were deferred deliberately by the migration councils, not
forgotten. Severity reflects impact, not effort.

Status legend: **[planned]** agreed, not started · **[idea]** worth doing, undecided.

---

## Phase 7 — Hardening (the four big ones)

### 7.1 Installable package  [planned]
Promote `bin/_lib/` to an installable package (`maicelium/` + `pyproject.toml`,
installed via `uv pip install -e .` or `pip install -e .`) with console entry
points. Removes the per-script `sys.path` bootstrap and the `tests/` path shims,
enables `mypy`, and makes the CLI invokable as `maicelium-sync` etc. regardless of
CWD. Deferred because adding a build/install step in `init.py` is exactly the
friction we wanted to avoid on Windows-native first runs.

### 7.2 Single-orchestrator CLI  [idea]
Collapse the ~13 individual scripts into one entry point: `maicelium <subcommand>`
(`maicelium sync`, `maicelium project add`, `maicelium layer add`, …). One hooks/
permissions surface, `--help` discovery, easier shipping. Keep thin `bin/*.py`
wrappers for backward compatibility. Pairs naturally with 7.1.

### 7.3 CI matrix  [planned]
GitHub Actions workflow running `pytest` on a Linux + Windows (Developer Mode ON)
matrix on every push/PR, plus a `requirements-dev.txt` pinning `pytest`. This is
what turns "Windows works today" into "Windows stays working" and makes the
cross-platform guarantee continuous instead of manual. (Was BUG-08 in the
post-implementation council.)

### 7.4 WORKSPACE.md parser → PyYAML/TOML  [idea, conditional]
The current YAML-light parser/writer in `bin/_lib/workspace.py` and
`bin/_lib/workspace_writer.py` is hand-rolled (zero external deps, intentional).
Migrate to PyYAML, or switch the on-disk format to TOML (`tomllib`, stdlib), **only
if** parser fragility produces ≥3 real issues. Until then the hand-rolled parser is
covered by fixtures and stays dependency-free.

---

## Smaller follow-ups (admissible items from the councils)

- **Drift detection ignores mode/ownership** — `bin/sync_symlinks.py` `_deep_equal`
  uses `filecmp.cmp(shallow=False)` (content only). `--fix-drift` can therefore drop
  executable bits / ACLs when collapsing an identical reflection to a symlink.
  Either include `st_mode` in the comparison or document the limitation. [idea]
- **`separate_git` alias quoting** — `bin/separate_git.py` interpolates `git_backup`
  and workspace paths into the shell alias without `shlex.quote`; breaks on paths
  containing quotes/odd spaces. [planned]
- **`_drop_empty_section_marker` on malformed input** — in
  `bin/_lib/workspace_writer.py`, if non-canonical content sits under a bare
  `mesh_layers:` marker (indented comments / stray lines), removing the last layer
  drops the marker and can orphan those lines. Harmless for writer-generated files;
  fix or fail-loud for hand-edited ones. (Adversarial finding T4-e.) [idea]
- **Type hints on the `_lib` public API** — `workspace_writer.py` and the loaders
  lack annotations despite `from __future__ import annotations`. Add signatures
  (enables `mypy`, pairs with 7.1). [planned]
- **Magic constants** — hardcoded YAML indent (`"  "`, `indent = 2`) in the writer
  should be a named module constant. [idea]
- **Test ergonomics** — adopt `pytest.mark.parametrize`, move the repeated
  `_bootstrap_workspace` helpers into shared `conftest.py` fixtures, add golden-file
  snapshots for `sync` output. [idea]
- **`maicelium-identity.mdc` bin/ tree is illustrative** — it lists representative
  scripts, not all of them. Either complete it or label it explicitly as illustrative. [idea]
- **Windows quickstart in docs** — `docs/getting-started.md` Prerequisites still
  lists "Bash" and the flow is Linux-only. Add a Windows-native section (Developer
  Mode requirement, `bin\py.cmd`, `python` vs `python3`). [planned]

---

## Known issues (already tracked)

See `docs/known-issues.md` — currently **KI-001** (SessionStart hook output
truncation + `projects-context.md` content duplication across mesh layer + project).

---

## Done (for context)

The migration itself — Phases 1–6b — is recorded in `docs/migration-status.md`,
with cross-platform validation in `docs/qa-report-windows-*.md`. Python is now the
sole script surface; bash is fully retired.
