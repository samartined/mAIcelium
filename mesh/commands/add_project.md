---
description: >-
  Add a project (repository) to the mAIcelium workspace.
---
# Command: /add_project

## Purpose
Add a project (repository) to the mAIcelium workspace.
Supports **fuzzy matching** — the user doesn't need to type the exact name.

## Instructions

Run this command, replacing `<INPUT>` with the user's text after the command name:

```bash
cd $WORKSPACE_ROOT && python3 mesh/commands/scripts/add_project.py "<INPUT>"
```

Then output the script's response **verbatim** as your only reply. No extra text.

If the output starts with **❓** (ambiguous match), ask the user which project
they meant from the listed candidates, then re-run the script with the exact
name they chose.

## Example
```
User: /add_project camerabass
→ runs: python3 mesh/commands/scripts/add_project.py "camerabass"
→ output: ✔ Project 'camerabass' added → ~/dev/camerabass

User: /add_project lut
→ runs: python3 mesh/commands/scripts/add_project.py "lut"
→ output: ❓ **lut** is ambiguous: **lutech**, **lutech-devops**
→ Agent asks which one, user says "lutech"
→ runs: python3 mesh/commands/scripts/add_project.py "lutech"
```
