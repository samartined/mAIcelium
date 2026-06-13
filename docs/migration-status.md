# Migration status: bash → Python

## Current phase: Phase 6b (dual-track removed, Python-only) — COMPLETED 2026-06-12

The bash-to-Python migration has reached its final phase: all original
`bin/*.sh` scripts (dual-track) have been removed, leaving Python as the
sole orchestration surface. The 13 bash scripts that coexisted during
Phase 6a are no longer present. Bash permissions (`Bash(bash:bin/*)`,
`Bash(bash:bin/hooks/*)`) have been removed from `.claude/settings.json`.
All framework operations are now routed exclusively through Python
(`bin/py.sh` / `bin/py.cmd`).

## Phase 6b completion: validation summary

The documented trigger ("7 days clean + Linux/WSL2/Windows matrix green")
was deliberately superseded: its goal — cross-platform confidence — was
met empirically by other means, and the calendar wait added no signal
without real usage in the window. The decisive points:

1. **The bash fallback never worked on Windows anyway.** Git Bash does not
   create symlinks reliably (`sync_symlinks.sh` exited non-zero in the
   Windows QA run), so removing it does not drop a usable Windows fallback.

2. **Cross-platform validation actually performed**:
   - **Linux** (real bash ↔ Python parity, native symlinks): byte-identical
     output across symlink set/targets, the three MCP JSON files,
     `mAIcelium.code-workspace`, and `.claude/projects-context.md`.
   - **Windows with Developer Mode ON**: 148 tests passing, 6/8 QA blocks
     PASS; the 2 failing blocks were the `remove_mesh_layer` empty-marker
     bug, since fixed (PR #2). Suite is 152 green after the `guard_write`
     `~/.claude/plans/` hotfix.
   - **WSL2**: not run explicitly. WSL2 is a real Linux kernel with POSIX
     symlinks, so the Linux validation covers its behaviour; the only
     differential risk (`/mnt/c` cross-FS) is unaffected by this change.

3. **Artifacts removed**:
   - All 13 original `bin/**/*.sh` scripts deleted (except `bin/py.sh`,
     which remains as the universal runner).
   - `Bash(bash:bin/*)` and `Bash(bash:bin/hooks/*)` permissions removed
     from `.claude/settings.json`.
   - References in `.smug.yml`, `docs/architecture.md`, `docs/reference.md`,
     and `README.md` updated to point to `.py` equivalents.

## Next gate: PR merge to main

A PR (`feat/windows-python-migration` → `main`) is currently under review
as the final gate before Phase 6b is considered closed. Once merged, the
dual-track phase is fully archived in production.

## Out of scope: Phase 7 hardening (deferred to post-main backlog)

The following items were explicitly deferred by the migration council
and are NOT bundled with Phase 6b:

- Packaging as an installable `maicelium/` package (`pyproject.toml`,
  entry points).
- Single-orchestrator CLI (`bin/maicelium <subcommand>`).
- Migration from the ad-hoc WORKSPACE.md parser-writer to PyYAML or
  TOML (only if ≥3 parser-fragility issues are reported).

These remain as backlog items in Phase 7, each with its own admissibility
review before action. Phase 7 is scheduled for post-main planning.
