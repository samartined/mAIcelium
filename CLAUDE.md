# mAIcelium Workspace

## What is this
Centralized multi-project workspace. This directory is open
simultaneously in Cursor, Claude Code, and Antigravity.

Projects connect via symlinks — they can live anywhere on disk.

## Rules — always read before acting
All rules live in `./ai/rules/`. Apply them without exception.

## Available skills
In `./ai/skills/`. Check the relevant SKILL.md before executing any task.
- `_common/`  — universal skills
- `_clients/` — client-specific skills
- `_domains/` — tech stack skills

## Active projects
Projects live in `./projects/` as symlinks to real repos.
Check `WORKSPACE.md` to see which ones are active.

## Mandatory workflow
1. Read WORKSPACE.md — know which projects are active.
2. Ask the user which project to focus on if not specified.
3. Work ONLY inside `projects/<project-name>/`.
4. Do not modify anything in `ai/`, `.cursor/`, `.claude/`, or `.antigravity/`.

## Available commands
- `/add_project <name> <path>`  → runs `bin/add_project.sh`
- `/remove_project <name>`      → runs `bin/remove_project.sh`
- `/workspace_status`           → current workspace state

## Repository index
Check `repos/_registry.yaml` for all available repos with their
paths and tech stacks before running /add_project.

## IDE responsibilities
| IDE          | Role                                      |
|--------------|-------------------------------------------|
| Claude Code  | Planning, architecture, analysis          |
| Cursor       | Code implementation                       |
| Antigravity  | Refactoring, review, scoped tasks         |

## Language
Always respond in Spanish. Code and technical artifacts stay in English.

## Project-specific context
For active project rules and skills, read `.claude/projects-context.md`.
