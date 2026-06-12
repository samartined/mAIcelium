---
description: >-
  Remove a project from the workspace. The original repo is never touched.
---
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

## Safety
NEVER run rm -rf. Only remove the symlink.
