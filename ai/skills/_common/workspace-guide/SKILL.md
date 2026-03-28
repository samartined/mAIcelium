# Skill: Workspace Guide

## When to use
- When an agent needs to create or modify AI configuration (rules, skills, commands, prompts).
- When an agent is unsure where to place a new file in the workspace.
- Automatically applied as orientation for any agent starting work in this workspace.

## Core principle

> **Always write AI resources to the `ai/` directory, never to the symlinked
> dotfolders (`.cursor/`, `.claude/`, `.antigravity/`).**

The dotfolders are auto-generated via symlinks. Any direct write to them will
either be overwritten on the next `bin/sync_symlinks.sh` run or create
inconsistencies between IDEs.

## File organization

| Resource  | Location                              | Format              |
|-----------|---------------------------------------|----------------------|
| Rules     | `ai/rules/<rule-name>.md`             | Markdown             |
| Skills    | `ai/skills/<category>/<name>/SKILL.md`| Markdown with frontmatter |
| Commands  | `ai/commands/<command-name>.md`       | Markdown             |
| Scripts   | `ai/commands/scripts/<name>.py`       | Python               |
| Prompts   | `ai/prompts/<prompt-name>.md`         | Markdown with placeholders |

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
ai/                          ← Single source of truth
├── rules/                   ← Global rules (all agents, all IDEs)
├── skills/                  ← Organized by category
├── commands/                ← Command definitions + scripts
└── prompts/                 ← Reusable templates

.cursor/rules/       → symlinks to ai/rules/*.md
.cursor/skills-cursor/ → symlinks to ai/skills/_common/*/ and _domains/*/
.antigravity/rules   → symlink to ai/rules/
.antigravity/skills  → symlink to ai/skills/
.claude/             → reads CLAUDE.md as entry point, projects-context.md for project rules
```

## What NOT to do

- ❌ Never edit files directly in `.cursor/`, `.claude/`, or `.antigravity/`.
- ❌ Never create new rules/skills in the dotfolders.
- ❌ Never move or rename files in dotfolders (they're symlinks).
- ❌ Never delete symlinks manually — use `bin/sync_symlinks.sh` to rebuild.
- ❌ Never modify `WORKSPACE.md` or `.claude/projects-context.md` by hand — they're auto-generated.
