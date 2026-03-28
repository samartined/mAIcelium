# Command: /add_project

## Purpose
Add a project (repository) to the mAIcelium workspace.

## Steps
1. If the user hasn't provided name and path, ask for them.
2. Check repos/_registry.yaml to validate the repo is registered.
3. Run: `bin/add_project.sh <name> <absolute_path>`
4. Confirm the symlink was created in projects/.
5. Show updated WORKSPACE.md.

## Example
User: /add_project my-api ~/repos/my-api
Agent runs: bin/add_project.sh my-api ~/repos/my-api
