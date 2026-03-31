---
description: >-
  Show the complete workspace status.
---
# Command: /workspace_status

## Purpose
Show the complete workspace status.

## Steps
1. Run `python3 mesh/commands/scripts/list_projects.py` to show linked projects.
2. Run `ls -la projects/` to verify symlinks.
3. Verify symlink integrity in `.cursor/`, `.claude/`, `.agents/`.
4. Show summary:
   - Active projects
   - Available skills in `mesh/skills/`
   - Active rules in `mesh/rules/`
   - Symlink status per IDE
