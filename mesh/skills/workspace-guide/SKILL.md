---
name: workspace-guide
description: >-
  - When an agent needs to create or modify AI configuration (rules, skills, commands, prompts). - When an agent is unsure where to place a new file in the workspace. - Automatically applied as orientation for any agent starting work in this workspace.
---
# Skill: Workspace Guide

## When to use
- When an agent needs to create or modify AI configuration (rules, skills, commands, prompts).
- When an agent is unsure where to place a new file in the workspace.
- Automatically applied as orientation for any agent starting work in this workspace.

## Core principle

> **Always write AI resources to their canonical source of truth. Edit layers
> directly; never edit the `mesh/` reflections of layer content; never edit
> the `.cursor/`, `.claude/`, `.agents/` dotfolders.**

There are two reflection tiers, and the agent must distinguish them:

```
mesh/layers/<layer>/...             ← TIER 1 source of truth (external repo, own .git)
         ↓  (symlink)
mesh/{skills,rules}/{_common,_domains,_clients}/...   ← tier-1 reflection (gitignored)
         ↓  (symlink)
.cursor/, .agents/, .claude/...                       ← tier-2 reflection (IDE dotfolders)
```

Writes to the dotfolders are rejected outright by the `guard-write.sh` hook.
Writes to stale tier-1 reflections (real files under `mesh/skills/_common|_domains|_clients/`
or `mesh/rules/_domains|_clients/` whose realpath stays inside `mesh/` instead
of descending into `mesh/layers/`) are also rejected. The agent must edit the
layer path directly and commit inside the layer repo.

## Layer vs reflection — decision tree

Before editing any skill or rule:

1. Identify the path you intend to write to.
2. If it is under `mesh/skills/{_common,_domains,_clients}/…` or
   `mesh/rules/{_domains,_clients}/…`, resolve its real path:
   ```bash
   python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" <file>
   ```
   - Realpath is under `mesh/layers/<layer>/…` → the reflection is a proper
     symlink. Editing the reflection writes the layer transparently, but
     prefer addressing the layer path directly and always commit inside the
     **layer repo** (every layer has its own `.git`), not in mAIcelium.
   - Realpath is still under `mesh/skills/` or `mesh/rules/` → **stale drift**.
     STOP. Port the change to the matching `mesh/layers/<layer>/…` path,
     commit inside the layer repo, then run `bin/sync_symlinks.sh --fix-drift`
     to convert the reflection to a symlink.
3. If the path is `mesh/rules/<name>.mdc`, `mesh/skills/<name>/SKILL.md`
   (flat, not under `_common|_domains|_clients`), `mesh/commands/…`,
   `mesh/prompts/…`, `mesh/mcp/…`, or anywhere under `bin/`, it is a
   mAIcelium-native resource. Edit directly and commit in the mAIcelium repo.

To list all active drift at any time:
```bash
bin/sync_symlinks.sh
```
The script prints a `⚠️ Layer-managed drift detected: N reflection(s)`
section at the end of every run when drift exists.

## File organization (canonical sources of truth)

| Resource                      | Location                                                            | Format                  |
|-------------------------------|---------------------------------------------------------------------|-------------------------|
| Native rule (mAIcelium)       | `mesh/rules/<name>.mdc`                                             | Markdown w/ frontmatter |
| Native skill (mAIcelium)      | `mesh/skills/<name>/SKILL.md`                                       | Markdown w/ frontmatter |
| Domain rule (shared)          | `mesh/layers/<layer>/rules/_domains/<domain>/<name>.mdc`            | Markdown w/ frontmatter |
| Client rule (shared)          | `mesh/layers/<layer>/rules/<name>.mdc`                              | Markdown w/ frontmatter |
| Universal skill (shared)      | `mesh/layers/<layer>/skills/_common/<name>/SKILL.md`                | Markdown w/ frontmatter |
| Domain skill (shared)         | `mesh/layers/<layer>/skills/_domains/<domain>/<name>/SKILL.md`      | Markdown w/ frontmatter |
| Client skill (shared)         | `mesh/layers/<layer>/skills/<name>/SKILL.md`                        | Markdown w/ frontmatter |
| Commands                      | `mesh/commands/<name>.md`                                           | Markdown                |
| Scripts                       | `mesh/commands/scripts/<name>.py`                                   | Python                  |
| Prompts                       | `mesh/prompts/<name>.md`                                            | Markdown + placeholders |

### Native vs shared — how to decide

A rule or skill is **mAIcelium-native** (lives directly in mAIcelium) when
it describes the workspace itself: architecture, conventions, hooks, slash
commands, identity. It has no reusable value outside this repo.

A rule or skill is **shared** (lives in a layer) when it encodes reusable
engineering practices, domain knowledge, IDE tooling, or client-specific
runbooks that any mAIcelium-style workspace could adopt by mounting the
same layer.

Examples of native: `workspace-guide`, `workspace-conventions`,
`maicelium-identity`, `commit-conventions`, `ai-files-language`.

Examples of shared (in layer `core`): `terraform-workflow`, `gcp-iam`,
`incident-response`, `code-review`, `refactoring`, `debug`,
`documentation`, `cursor-workspace-migration`.

### Layer routing — how `sync_symlinks.sh` classifies content

Layers do not carry metadata. Classification is **structural**, driven by
folder names plus the `client:` field declared in `WORKSPACE.md`. Only
`_common` and `_domains` are reserved; any other folder is routed to the
client bucket of that layer.

| Path inside the layer                         | Reflected into                                  |
|-----------------------------------------------|-------------------------------------------------|
| `skills/_common/<sk>/`                        | `mesh/skills/_common/<sk>/`                     |
| `skills/_domains/<sk>/`                       | `mesh/skills/_domains/<sk>/`                    |
| `skills/<other>/`                             | `mesh/skills/_clients/<client>/<other>/`        |
| `rules/_domains/<domain>/<r>.mdc`             | `mesh/rules/_domains/<domain>/<r>.mdc`          |
| `rules/<r>.mdc` (flat at the layer root)      | `mesh/rules/_clients/<client>/<r>.mdc`          |

Three rules to keep in mind when authoring or moving content:

1. A layer must be **registered in `WORKSPACE.md → mesh_layers:`** for the
   sync to see it. A layer present on disk but unregistered is invisible.
2. To change the bucket of a skill or rule, **move the directory inside the
   owning layer** (between `_common/`, `_domains/<domain>/`, or flat) and
   re-run `bin/sync_symlinks.sh`. Editing the reflection has no effect.
3. `client:` defaults to `name` if omitted. It only controls the namespace
   of the `_clients/<client>/…` bucket.

Lifecycle commands:

```bash
bin/add_mesh_layer.sh <name> <path> [--client <name>] [--repo <url>]
bin/remove_mesh_layer.sh <name>
```

The full convention (including the authoring decision tree) lives in
`mesh/rules/workspace-conventions.mdc` under "Layer routing convention".

## Skill categories

- `_common/`  — Universal skills (any tech stack, any project)
- `_clients/` — Client-specific skills (scoped to a client's conventions)
- `_domains/` — Tech-stack-specific skills (React, Python, DevOps, etc.)

## Naming conventions

- Use **kebab-case** (hyphen-separated lowercase) for all file and directory names.
- Skill directory names: max 64 characters.
- Keep SKILL.md files under 500 lines.
- Rule files: descriptive name reflecting the rule's scope (e.g., `security-checklist.md`).

## Command response format

All slash commands should produce responses that end with an emoji-prefixed
status line:

| Emoji | Meaning     | Example                                        |
|-------|-------------|------------------------------------------------|
| ✅    | Success     | `✅ Pushed to **origin/main** — abc1234`       |
| ✔     | Step done   | `✔ Project 'my-api' added → ~/dev/my-api`     |
| ⚠️    | Warning     | `⚠️ Project 'my-api' is already linked.`       |
| ❌    | Error       | `❌ Path does not exist: ~/dev/missing`         |
| ❓    | Ambiguous   | `❓ **lut** is ambiguous: **lutech**, **lutech-devops**` |
| 🗑️    | Removed     | `🗑️ **my-api** unlinked.`                      |
| 📭    | Empty       | `📭 No projects are currently linked.`          |

## Symlink architecture

```
mesh/                          ← Single source of truth
├── rules/                   ← Global rules (all agents, all IDEs)
│   └── _domains/            ← Domain-scoped rules (e.g., software/)
├── skills/                  ← Organized by category
│   ├── _common/             ← Universal skills
│   ├── _domains/            ← Tech-stack skills (e.g., obsidian/, backend-python/)
│   └── _clients/            ← Client-specific skills
├── commands/                ← Command definitions + scripts
└── prompts/                 ← Reusable templates

.cursor/rules/       → symlinks to mesh/rules/*.md + _domains/*/*.md (prefixed domain--)
.cursor/skills-cursor/ → symlinks to mesh/skills/_common/*/ and _domains/*/
.agents/skills/      → symlink to flattened mesh/skills/
.agents/workflows/   → symlink to mesh/commands/
.claude/             → reads CLAUDE.md as entry point, projects-context.md for project rules
```

## What NOT to do

- ❌ Never edit files directly in `.cursor/`, `.claude/`, or `.agents/`.
- ❌ Never edit stale tier-1 reflections under `mesh/{skills,rules}/{_common,_domains,_clients}/…` — edit the matching layer path.
- ❌ Never create new rules/skills in the dotfolders.
- ❌ Never move or rename files in dotfolders (they're symlinks).
- ❌ Never delete symlinks manually — use `bin/sync_symlinks.sh` to rebuild.
- ❌ Never modify `WORKSPACE.md` or `.claude/projects-context.md` by hand — they're auto-generated.
- ❌ Never run `bin/sync_symlinks.sh --fix-drift` when the drift report shows `divergent` entries — resolve them first by porting the delta to the layer.
