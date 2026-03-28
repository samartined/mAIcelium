#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
NAME="$1"

if [ -z "$NAME" ]; then
  echo "Usage: remove_project.sh <name>"
  echo ""
  echo "Active projects:"
  ls "$ROOT/projects/" 2>/dev/null || echo "  (none)"
  exit 1
fi
if [[ ! "$NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "❌ Invalid project name '$NAME'. Only letters, numbers, hyphens and underscores allowed."
  exit 1
fi

LINK="$ROOT/projects/$NAME"
if [ ! -L "$LINK" ]; then
  echo "❌ Project '$NAME' does not exist in the workspace."
  exit 1
fi

# ── Remove project-specific Cursor rules ─────────────────────────────────────
REMOVED_RULES=0
for rule in "$ROOT"/.cursor/rules/${NAME}--*; do
  [ -L "$rule" ] || continue
  rm "$rule"
  echo "  - $(basename "$rule")"
  REMOVED_RULES=$((REMOVED_RULES + 1))
done
[ "$REMOVED_RULES" -gt 0 ] && echo "  ✔ $REMOVED_RULES project rule(s) removed"

# ── Remove project-specific Cursor skills ────────────────────────────────────
REMOVED_SKILLS=0
for skill in "$ROOT"/.cursor/skills-cursor/${NAME}--*; do
  [ -L "$skill" ] || continue
  rm "$skill"
  echo "  - $(basename "$skill")"
  REMOVED_SKILLS=$((REMOVED_SKILLS + 1))
done
[ "$REMOVED_SKILLS" -gt 0 ] && echo "  ✔ $REMOVED_SKILLS project skill(s) removed"

# ── Remove project symlink ───────────────────────────────────────────────────
rm "$LINK"
echo "✔ Project '$NAME' removed from workspace (original repo untouched)"

# ── Update WORKSPACE.md ──────────────────────────────────────────────────────
python3 -c '
import sys, os
root, name = sys.argv[1], sys.argv[2]
wf = os.path.join(root, "WORKSPACE.md")
with open(wf) as f:
    lines = f.readlines()
out, skip = [], False
for line in lines:
    if line.strip().startswith("- name: " + name):
        skip = True
    elif skip and line.startswith("  "):
        continue
    else:
        skip = False
        out.append(line)
with open(wf, "w") as f:
    f.writelines(out)
print("  ✔ WORKSPACE.md updated")
' "$ROOT" "$NAME"

# ── Regenerate Claude Code project context ────────────────────────────────────
_regenerate_claude_context "$ROOT"
echo "  ✔ Claude project context updated"
