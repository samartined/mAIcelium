# Known Issues

## KI-001 — SessionStart hook truncation breaks rule injection

**Date detected**: 2026-04-17
**Severity**: High
**Status**: Resolved/Mitigated (2026-06-18)

### Description

The original SessionStart hook in `.claude/settings.json` outputted the full contents of `.claude/projects-context.md` via `cat`, which Claude Code truncated at ~2KB. The file weighed 204KB/4913 lines, so only the first ~70 lines ever reached the assistant and all project-specific rules were invisible.

The hook also had a CP1252 mojibake risk on Windows: the failure-branch message contained an em-dash character (`—`, U+2014) which is not representable in CP1252 and would corrupt the message on Windows systems.

### Root causes (historical)

1. **Hook output was 100x the truncation limit.** The `cat` of `projects-context.md` output 204KB; Claude Code exposed ~2KB.

2. **The CLAUDE.md fallback was silently defeated.** Because hook output resembled the beginning of the file, the assistant inferred context was already loaded and skipped the explicit Read.

3. **Massive content duplication inflated the file 2-3x.** Project rules appeared twice - once under the mesh layer and once as a standalone project section.

### Resolution

Both issues are mitigated as of this branch (fix/hook-truncation-KI-001, TR-10 / #21):

**Hook no longer cats the file.** The SessionStart command now emits a short read-instruction message instead:

```json
"command": "bin/py.sh bin/sync_symlinks.py > /dev/null && echo \"Context synced. Read .claude/projects-context.md for workspace and project rules.\" || echo \"sync_symlinks.py failed - context may be stale. Read .claude/projects-context.md.\""
```

The assistant receives a concise message and must explicitly `Read .claude/projects-context.md` to load the full context. Both `bin/init.py` (the generator) and the committed `.claude/settings.json` have been updated and are byte-consistent.

**CP1252 safety.** The failure-branch message now uses an ASCII hyphen (`-`) instead of an em-dash. The command string is fully ASCII-safe (`cmd.isascii()` is `True`). Regression tests lock this behavior.

**Dedup mechanism.** The `context_inline: false` project flag suppresses inlining a project's rules/skills when it is already covered by a mesh layer. A project covered by a mesh layer should be flagged in `WORKSPACE.md`:

```yaml
projects:
  - name: myproject
    path: /abs/myproject
    context_inline: false
```

This flag is per-machine configuration (WORKSPACE.md is gitignored) and must be set via `bin/set_project_flag.py` on each initialized workspace.

### Operational note

To prevent duplication for projects that are also covered by a mesh layer, flag them `context_inline: false` using the project-flag command:

```
bin/py.sh bin/set_project_flag.py <project-name> context_inline false
```

This is per-machine configuration and is not tracked in git.

### Incident

Discovered while resolving SM00001-163159 (Tiber IAM grant). The tiber-specific rules (`tiber--bitacora`, `tiber--jira-workflow`, `tiber--commit-workflow`, `tiber--plans-storage`) were completely invisible. The ticket was resolved without following the mandatory bitácora/plan/worklog workflows, and the Jira comment was sent without human review.
