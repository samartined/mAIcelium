# Agent Configuration — mAIcelium

## Global rules for all agents
- Always read `./mesh/rules/global.md` before any action.
- Never modify files in `.cursor/`, `.claude/`, `.agents/` (auto-generated).
- New AI resources go in `mesh/` — see `mesh/skills/_common/workspace-guide/SKILL.md`.
- Only work inside the indicated project in `projects/`.
- Never run `rm -rf` on symlink targets in `projects/`.

## Allowed permissions
- Full read access to the workspace.
- Write access only inside `projects/<active-project>/`.
- Write access inside `mesh/` for new rules, skills, commands, and prompts.
- Execution of scripts in `bin/`.
- Execution of scripts in `bin/hooks/` (PreToolUse security checks).
- Execution of Python scripts: `python3 mesh/commands/scripts/*.py`.

## Multi-agent coordination
When two agents work on the same project simultaneously,
conflicts are resolved at the git level as if they were two developers.
Each agent must make atomic, descriptive commits.

## Language
Agents respond in Spanish. Code and technical artifacts stay in English.
