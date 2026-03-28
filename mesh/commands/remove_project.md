# Command: /remove_project

## Purpose
Remove a project from the workspace. The original repo is never touched.
Supports **fuzzy matching** against currently linked projects.

## Instructions

Run this command, replacing `<INPUT>` with the user's text after the command name:

```bash
cd $WORKSPACE_ROOT && python3 mesh/commands/scripts/remove_project.py "<INPUT>"
```

Then output the script's response **verbatim** as your only reply. No extra text.

If the output starts with **❓** (ambiguous match), ask the user which project
they meant from the listed candidates, then re-run with the exact name.

## Fallback

If the Python script is unavailable:

1. If the user hasn't provided a name, show active projects and ask.
2. Run: `bin/remove_project.sh <name>`
3. Confirm the symlink was removed from `projects/`.
4. Confirm the original repo remains intact.
5. Show updated WORKSPACE.md.

## Safety
NEVER run rm -rf. Only remove the symlink.
