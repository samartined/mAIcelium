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

> **Always write AI resources to the `mesh/` directory, never to the symlinked
> dotfolders (`.cursor/`, `.claude/`, `.agents/`).**

The dotfolders are auto-generated via symlinks. Any direct write to them will
either be overwritten on the next `bin/sync_symlinks.py` run or create
inconsistencies between IDEs.

## File organization

| Resource       | Location                                        | Format              |
|----------------|------------------------------------------------|----------------------|
| Global rules   | `mesh/rules/<name>.md`                          | Markdown             |
| Domain rules   | `mesh/rules/_domains/<domain>/<name>.md`        | Markdown             |
| Skills         | `mesh/skills/<category>/<name>/SKILL.md`        | Markdown with frontmatter |
| Commands       | `mesh/commands/<name>.md`                       | Markdown             |
| Scripts        | `mesh/commands/scripts/<name>.py`               | Python               |
| Prompts        | `mesh/prompts/<name>.md`                        | Markdown with placeholders |

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
- ❌ Never create new rules/skills in the dotfolders.
- ❌ Never move or rename files in dotfolders (they're symlinks).
- ❌ Never delete symlinks manually — use `bin/sync_symlinks.py` to rebuild.
- ❌ Never modify `WORKSPACE.md` or `.claude/projects-context.md` by hand — they're auto-generated.
