# Migration status: bash → Python

## Current phase: Phase 6a (Python set complete, dual-track)

The mAIcelium framework scripts have been ported from bash to Python in
parallel with the existing `bin/*.sh` originals. Both sets coexist; the
`.claude/settings.json` `SessionStart` and `PreToolUse` hooks invoke the
Python versions exclusively. Bash permissions (`Bash(bash:bin/*)`,
`Bash(bash:bin/hooks/*)`) remain allowed as a fallback during the
quarantine period.

## Trigger for Phase 6b (delete `.sh`)

The bash scripts and their permissions will be removed once **all** of
the following conditions are satisfied:

1. **No regression for 7 consecutive days** in real workspace use:
   - `.claude/hook-failures.log` is empty (no `ValueError`, no
     `stdin-parse-error`, no `timeout`).
   - `SessionStart` logs report `Context synced.` every session.
   - No reports from users / integrators of unexpected behaviour.

2. **Cross-platform smoke test passes** on at least:
   - Linux clean (Ubuntu 22.04 LTS, Python 3.10+).
   - WSL2.
   - Windows native with Developer Mode ON.

When both conditions hold, open a single PR that:

- Removes every `bin/**/*.sh` except `bin/py.sh`.
- Removes `Bash(bash:bin/*)` and `Bash(bash:bin/hooks/*)` from
  `.claude/settings.json` `permissions.allow`.
- Updates `.smug.yml`, `docs/architecture.md`, `docs/reference.md`,
  `README.md` to reference the `.py` scripts.

## Out of scope: Phase 7 hardening (deferred)

The following items were explicitly deferred by the migration council
and are NOT bundled with Phase 6b:

- Packaging as an installable `maicelium/` package (`pyproject.toml`,
  entry points).
- Single-orchestrator CLI (`bin/maicelium <subcommand>`).
- Migration from the ad-hoc WORKSPACE.md parser-writer to PyYAML or
  TOML (only if ≥3 parser-fragility issues are reported).

These remain as backlog items, each with its own admissibility review
before action.
