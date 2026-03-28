# Command: /remove_project

## Purpose
Remove a project from the workspace. The original repo is never touched.

## Steps
1. If the user hasn't provided a name, show active projects and ask.
2. Run: `bin/remove_project.sh <name>`
3. Confirm the symlink was removed from projects/.
4. Confirm the original repo remains intact at its path.
5. Show updated WORKSPACE.md.

## Safety
NEVER run rm -rf. Only remove the symlink.
