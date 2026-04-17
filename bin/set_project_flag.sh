#!/usr/bin/env bash
# set_project_flag.sh — Set or update a flag on a project entry in WORKSPACE.md.
#
# Usage:
#   bash bin/set_project_flag.sh <project-name> <flag> <value>
#
# Examples:
#   bash bin/set_project_flag.sh maicelium-private context_inline false
#   bash bin/set_project_flag.sh maicelium-private context_inline true
#
# Supported flags:
#   context_inline  — when false, project is listed but rules/skills are not
#                     inlined in .claude/projects-context.md (avoids duplication
#                     from framework repos whose .cursor/ holds all mesh symlinks)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$ROOT/WORKSPACE.md"

PROJECT="${1:-}"
FLAG="${2:-}"
VALUE="${3:-}"

if [ -z "$PROJECT" ] || [ -z "$FLAG" ] || [ -z "$VALUE" ]; then
  echo "Usage: bash bin/set_project_flag.sh <project-name> <flag> <value>" >&2
  echo "Example: bash bin/set_project_flag.sh maicelium-private context_inline false" >&2
  exit 1
fi

if [ ! -f "$WORKSPACE" ]; then
  echo "Error: WORKSPACE.md not found at $WORKSPACE" >&2
  exit 1
fi

# Use Python to safely update or insert the flag in the YAML-like WORKSPACE.md
python3 - "$WORKSPACE" "$PROJECT" "$FLAG" "$VALUE" <<'PYEOF'
import sys, re

workspace_file = sys.argv[1]
project_name   = sys.argv[2]
flag_key       = sys.argv[3]
flag_value     = sys.argv[4]

with open(workspace_file) as f:
    lines = f.readlines()

in_projects = False
in_target   = False
target_end  = None
flag_line   = None
insert_after = None  # line index after which to insert the flag

for i, line in enumerate(lines):
    stripped = line.strip()

    if stripped == 'projects:':
        in_projects = True
        continue

    if not in_projects:
        continue

    # End of projects section
    if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
        if in_target:
            target_end = i
        break

    if stripped.startswith('- name:'):
        name = stripped.split(':', 1)[1].strip()
        if in_target and target_end is None:
            target_end = i
        in_target = (name == project_name)
        if in_target:
            insert_after = i

    if in_target:
        if stripped.startswith(f'{flag_key}:'):
            flag_line = i
        elif stripped and not stripped.startswith('#'):
            # Track last meaningful line of this entry for insertion point
            insert_after = i

if not in_target and target_end is None:
    print(f"Error: project '{project_name}' not found in WORKSPACE.md", file=sys.stderr)
    sys.exit(1)

if flag_line is not None:
    # Update existing flag
    old = lines[flag_line]
    indent = len(old) - len(old.lstrip())
    lines[flag_line] = ' ' * indent + f'{flag_key}: {flag_value}\n'
    action = 'updated'
else:
    # Insert new flag after the last line of this project entry
    indent = 2  # standard YAML list item indent
    new_line = ' ' * indent + f'{flag_key}: {flag_value}\n'
    lines.insert(insert_after + 1, new_line)
    action = 'added'

with open(workspace_file, 'w') as f:
    f.writelines(lines)

print(f"OK: {action} '{flag_key}: {flag_value}' for project '{project_name}' in WORKSPACE.md")
PYEOF

# Regenerate context so the change takes effect immediately
echo "Regenerating context..."
# shellcheck source=bin/_lib.sh
source "$ROOT/bin/_lib.sh"
_regenerate_claude_context "$ROOT"
lines=$(wc -l < "$ROOT/.claude/projects-context.md")
size=$(wc -c < "$ROOT/.claude/projects-context.md")
echo "Done. projects-context.md: ${lines} lines / ${size} bytes"
