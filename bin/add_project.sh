#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
NAME="$1"
REPO_PATH="$(realpath "${2:-}" 2>/dev/null || echo "")"

if [ -z "$NAME" ] || [ -z "$REPO_PATH" ]; then
  echo "Usage: add_project.sh <name> <path>"
  exit 1
fi
if [[ ! "$NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "❌ Invalid project name '$NAME'. Only letters, numbers, hyphens and underscores allowed."
  exit 1
fi
if [ ! -d "$REPO_PATH" ]; then
  echo "❌ Path '$REPO_PATH' does not exist."
  exit 1
fi
if ! grep -q "$REPO_PATH" "$ROOT/repos/_registry.yaml" 2>/dev/null; then
  echo "⚠️  Warning: '$REPO_PATH' is not registered in repos/_registry.yaml"
  echo "   Consider adding it for agent discoverability."
fi

LINK="$ROOT/projects/$NAME"
if [ -L "$LINK" ]; then
  echo "⚠️  Project '$NAME' already exists. Use remove_project.sh first."
  exit 1
fi

ln -sfn "$REPO_PATH" "$LINK"
echo "✔ Project '$NAME' added → $REPO_PATH"

# ── Import project-specific Cursor rules ─────────────────────────────────────
PROJECT_CURSOR_RULES="$REPO_PATH/.cursor/rules"
if [ -d "$PROJECT_CURSOR_RULES" ]; then
  echo "  → Importing project rules..."
  for rule in "$PROJECT_CURSOR_RULES"/*; do
    [ -f "$rule" ] || continue
    rulename=$(basename "$rule")
    ln -sfn "$rule" "$ROOT/.cursor/rules/${NAME}--${rulename}"
    echo "    + ${NAME}--${rulename}"
  done
  echo "  ✔ Project rules imported"
fi

# ── Import project-specific Cursor skills ────────────────────────────────────
PROJECT_CURSOR_SKILLS="$REPO_PATH/.cursor/skills"
if [ -d "$PROJECT_CURSOR_SKILLS" ]; then
  echo "  → Importing project skills..."
  for skill_dir in "$PROJECT_CURSOR_SKILLS"/*/; do
    [ -d "$skill_dir" ] || continue
    skillname=$(basename "$skill_dir")
    ln -sfn "$skill_dir" "$ROOT/.cursor/skills-cursor/${NAME}--${skillname}"
    echo "    + ${NAME}--${skillname}"
  done
  echo "  ✔ Project skills imported"
fi

# Also check .cursor/skills-cursor/ (alternative location)
PROJECT_CURSOR_SKILLS_ALT="$REPO_PATH/.cursor/skills-cursor"
if [ -d "$PROJECT_CURSOR_SKILLS_ALT" ]; then
  echo "  → Importing project skills (skills-cursor/)..."
  for skill_dir in "$PROJECT_CURSOR_SKILLS_ALT"/*/; do
    [ -d "$skill_dir" ] || continue
    skillname=$(basename "$skill_dir")
    # Skip if already imported from .cursor/skills/
    [ -L "$ROOT/.cursor/skills-cursor/${NAME}--${skillname}" ] && continue
    ln -sfn "$skill_dir" "$ROOT/.cursor/skills-cursor/${NAME}--${skillname}"
    echo "    + ${NAME}--${skillname}"
  done
  echo "  ✔ Project skills imported"
fi

# ── Update WORKSPACE.md ──────────────────────────────────────────────────────
python3 -c '
import sys, datetime, os
root, name, repo_path = sys.argv[1], sys.argv[2], sys.argv[3]
wf = os.path.join(root, "WORKSPACE.md")
with open(wf) as f:
    content = f.read()
entry = "- name: {}\n  path: {}\n  added: {}Z".format(
    name, repo_path, datetime.datetime.utcnow().isoformat()
)
if "projects: []" in content:
    content = content.replace("projects: []", "projects:\n" + entry)
else:
    content = content.rstrip() + "\n" + entry + "\n"
with open(wf, "w") as f:
    f.write(content)
print("  ✔ WORKSPACE.md updated")
' "$ROOT" "$NAME" "$REPO_PATH"

# ── Regenerate Claude Code project context ────────────────────────────────────
_regenerate_claude_context "$ROOT"
echo "  ✔ Claude project context updated"

echo ""
echo "Active projects:"
ls -la "$ROOT/projects/" | grep "^l"
