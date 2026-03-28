# Command: /workspace_status

## Purpose
Show the complete workspace status.

## Steps
1. Run `python3 ai/commands/scripts/list_projects.py` to show linked projects.
2. Run `ls -la projects/` to verify symlinks.
3. Verify symlink integrity in `.cursor/`, `.claude/`, `.antigravity/`.
4. Show summary:
   - Active projects
   - Available skills in `ai/skills/`
   - Active rules in `ai/rules/`
   - Symlink status per IDE
