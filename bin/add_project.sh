#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
_load_conventions "$ROOT"
CODE_ONLY=false
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --code-only) CODE_ONLY=true; shift ;;
    *) echo "❌ Unknown flag '$1'"; exit 1 ;;
  esac
done

NAME="$1"
REPO_PATH="$(realpath "${2:-}" 2>/dev/null || echo "")"

if [ -z "$NAME" ] || [ -z "$REPO_PATH" ]; then
  echo "Usage: add_project.sh [--code-only] <name> <path>"
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
REGISTRY="$ROOT/repos/_registry.yaml"
REPO_PATH_HOME="${REPO_PATH/#$HOME/\~}"
if ! grep -q "$REPO_PATH" "$REGISTRY" 2>/dev/null && \
   ! grep -q "$REPO_PATH_HOME" "$REGISTRY" 2>/dev/null; then
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

if [ "$CODE_ONLY" = false ]; then
  # ── Import project-specific rules ─────────────────────────────────────────
  PROJECT_RULES_DIR="$REPO_PATH/$MESH_PROJECT_DATA_DIR/$MESH_PROJECT_RULES_SUBDIR"
  if [ -d "$PROJECT_RULES_DIR" ]; then
    echo "  → Importing project rules..."
    for rule in "$PROJECT_RULES_DIR"/*; do
      [ -f "$rule" ] || continue
      rulename=$(basename "$rule")
      ln -sfn "$rule" "$ROOT/.cursor/rules/${NAME}--${rulename}"
      echo "    + ${NAME}--${rulename}"
    done
    echo "  ✔ Project rules imported"
  fi

  # ── Import project-specific skills (all configured skills subdirs) ─────────
  for skills_subdir in $MESH_PROJECT_SKILLS_SUBDIRS; do
    PROJECT_SKILLS_DIR="$REPO_PATH/$MESH_PROJECT_DATA_DIR/$skills_subdir"
    [ -d "$PROJECT_SKILLS_DIR" ] || continue
    echo "  → Importing project skills ($skills_subdir/)..."
    for skill_dir in "$PROJECT_SKILLS_DIR"/*/; do
      [ -d "$skill_dir" ] || continue
      skillname=$(basename "$skill_dir")
      [ -L "$ROOT/.cursor/skills-cursor/${NAME}--${skillname}" ] && continue
      ln -sfn "$skill_dir" "$ROOT/.cursor/skills-cursor/${NAME}--${skillname}"
      echo "    + ${NAME}--${skillname}"
    done
    echo "  ✔ Project skills imported ($skills_subdir/)"
  done
else
  echo "  ⏭ Skipping rules/skills import (--code-only)"
fi

# ── Update WORKSPACE.md ──────────────────────────────────────────────────────
python3 -c '
import sys, datetime, os
root, name, repo_path = sys.argv[1], sys.argv[2], sys.argv[3]
wf = os.path.join(root, "WORKSPACE.md")
with open(wf) as f:
    content = f.read()
entry = "- name: {}\n  path: {}\n  added: {}".format(
    name, repo_path, datetime.datetime.now(datetime.UTC).isoformat()
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

# ── Regenerate multi-root workspace file ──────────────────────────────────────
_regenerate_workspace_file "$ROOT"
echo "  ✔ Workspace file updated (mAIcelium.code-workspace)"

echo ""
echo "Active projects:"
ls -la "$ROOT/projects/" | grep "^l"
