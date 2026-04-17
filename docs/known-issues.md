# Known Issues

## KI-001 — SessionStart hook truncation breaks rule injection

**Date detected**: 2026-04-17
**Severity**: High
**Status**: Open

### Description

The SessionStart hook in `.claude/settings.json` outputs the full contents of `.claude/projects-context.md`:

```json
"command": "bash bin/sync_symlinks.sh > /dev/null && cat .claude/projects-context.md"
```

The intent is to inject all workspace and project rules into the assistant's context. However, Claude Code truncates hook output at approximately 2KB, showing only a short preview. The file currently weighs **204KB / 4913 lines**, so only the first ~70 lines (3 generic workspace rules) ever reach the assistant. All project-specific rules are invisible.

### Root causes

1. **Hook output is 100x the truncation limit.** The `cat` of `projects-context.md` outputs 204KB; Claude Code exposes ~2KB. Project rules (starting at line 832 via `maicelium-private`, or line 3823 via `tiber`) never survive.

2. **The CLAUDE.md fallback is silently defeated.** CLAUDE.md instructs the assistant to "read `.claude/projects-context.md`" at every session start. But because the hook output already resembles the beginning of that file (same headers, same format), the assistant infers the context is already loaded and skips the explicit Read.

3. **Massive content duplication inflates the file 2–3x.** All 11 Tiber rules/skills appear twice — once under `maicelium-private` (134KB, injected via mesh layer) and once under `tiber` (48.5KB, injected as a standalone project). This results in ~183KB of near-identical content in a 204KB file.

### Content breakdown (as of 2026-04-17)

| Section | Lines | Bytes | Notes |
|---------|-------|-------|-------|
| Workspace rules | 1–301 | ~12KB | 5 global rules |
| `maicelium-private` | 308–3535 | **134KB** | Entire mesh layer incl. 11 tiber entries |
| `ms-dns-domains` | 3536–3538 | ~65B | Empty |
| `my-gcp-sandbox` | 3540–3542 | ~65B | Empty |
| `techcorpus` | 3544–3821 | ~8.5KB | Techcorpus rules+skills |
| `tiber` | 3823–4913 | **48.5KB** | Same 11 tiber rules+skills, duplicated |
| **Total** | **4913** | **204KB** | |

### Workaround (until fix is deployed)

At the start of every session, **explicitly read the file**:

```
Read .claude/projects-context.md
```

Do not assume the hook preview is the full context.

### Proposed fixes

| Fix | Effort | Impact |
|-----|--------|--------|
| Stop catting in hook — output a short sync-confirmation message instead | Trivial | High |
| Deduplicate mesh-layer content — emit shared rules once with cross-reference | Medium | High |
| Split into per-project files — `projects-context.md` becomes a lightweight index | Medium | Medium |
| Combined: short hook message + dedup + split | Medium | Highest |

### Incident

Discovered while resolving SM00001-163159 (Tiber IAM grant). The tiber-specific rules (`tiber--bitacora`, `tiber--jira-workflow`, `tiber--commit-workflow`, `tiber--plans-storage`) were completely invisible. The ticket was resolved without following the mandatory bitácora/plan/worklog workflows, and the Jira comment was sent without human review.
