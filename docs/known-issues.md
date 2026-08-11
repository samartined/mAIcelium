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

**Structural dedup for skills (2026-08-11).** The `context_inline: false` flag is a
per-machine opt-in that suppresses a project's rules *and* skills wholesale. Skill
duplication is now handled structurally instead, and independently of the flag:
`sync_symlinks.py` reflects mesh, layer, and project skills into `.claude/skills/`,
Claude Code's native skill directory, so it loads each `SKILL.md` on demand. With the
body reachable that way, `regenerate_claude_context` emits a skill *index* per project
rather than inlining bodies — removing the largest contributor to the 204KB file.
Rules are unaffected and still inlined in full.

A skill whose `SKILL.md` lacks `name` + `description` frontmatter cannot be registered
by Claude Code, so those are still inlined in full. Without that fallback, dropping the
body would turn a duplicated skill into an invisible one — the failure this KI is about.

### Operational note

To prevent duplication for projects that are also covered by a mesh layer, flag them `context_inline: false` using the project-flag command:

```
bin/py.sh bin/set_project_flag.py <project-name> context_inline false
```

This is per-machine configuration and is not tracked in git.

### Incident

Discovered while resolving SM00001-163159 (Tiber IAM grant). The tiber-specific rules (`tiber--bitacora`, `tiber--jira-workflow`, `tiber--commit-workflow`, `tiber--plans-storage`) were completely invisible. The ticket was resolved without following the mandatory bitácora/plan/worklog workflows, and the Jira comment was sent without human review.

## KI-002 — `mai` CLI: known limitations and intentional trade-offs

**Date detected**: 2026-06-24
**Severity**: Low
**Status**: Documented (by design)

### Description

The `mai` command router (`maicelium_cli.py`) ships with a few deliberate
limitations, pinned by tests so any future change is explicit:

- **Editable install only.** `mai` is supported via `pip install -e .` (or the
  committed `./mai` / `mai.cmd` shims). A non-editable wheel copies
  `maicelium_cli.py` into `site-packages` and severs its link to the sibling
  `bin/` directory, so a detached install must set `MAICELIUM_ROOT` (or run from
  inside a workspace). Detached/global install (packaging `bin/` + `mesh/` as data)
  is out of scope for now.
- **Exit code `2` is overloaded.** Router-level errors (unknown verb, bad
  `--root`, no resolvable workspace) use exit `2`, but child scripts also
  legitimately return `2` and `3` (e.g. `sync`), and `init` returns `2` without
  symlink privilege. Do **not** key CI gates on "exit 2 == bad invocation"; the
  child returncode is passed through verbatim.
- **`mai health` reports `0`/`2`, not `0`/`1`/`2`.** It exits `2` when a project
  symlink is broken and `0` otherwise. The intermediate "issues" tier (`1`) was
  dropped because existing tests pin no-git / no-README projects at exit `0`;
  reintroducing it requires redefining what counts as an "issue" and updating
  those tests.

### Resolution

These are accepted trade-offs, not bugs. Each is covered by a test so a future
decision to change the behavior is a deliberate red->green. See the council
decisions D1 (health) and D2 (distribution) in the PR history.
