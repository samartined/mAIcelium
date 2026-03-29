#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASENAME=$(basename "$ROOT")
GIT_BACKUP="${ROOT}-git-backup"

echo "🍄 Separating .git from mAIcelium workspace"
echo "   Workspace: $ROOT"
echo "   Git backup: $GIT_BACKUP"
echo ""

# ── Validate ─────────────────────────────────────────────────────────────────
if [ ! -d "$ROOT/.git" ]; then
  echo "❌ No .git directory found in $ROOT"
  echo "   Either already separated or not a git repo."
  exit 1
fi

if [ -d "$GIT_BACKUP" ]; then
  echo "❌ Backup directory already exists: $GIT_BACKUP"
  echo "   Remove it first if you want to re-separate."
  exit 1
fi

# ── Move .git to backup location ─────────────────────────────────────────────
mkdir -p "$GIT_BACKUP"
mv "$ROOT/.git" "$GIT_BACKUP/.git"
echo "  ✔ .git moved to $GIT_BACKUP/.git"

# ── Create shell alias file ──────────────────────────────────────────────────
ALIAS_FILE="$ROOT/bin/.git-alias.sh"
cat > "$ALIAS_FILE" << ALIASEOF
# mAIcelium git alias — source this in your shell profile
# Usage: maicelium-git <command>
#
# Example:
#   maicelium-git status
#   maicelium-git log --oneline
#   maicelium-git add -A && maicelium-git commit -m "msg" && maicelium-git push
#
alias maicelium-git='git --git-dir="$GIT_BACKUP/.git" --work-tree="$ROOT"'
ALIASEOF

# Replace with actual paths
sed -i "s|\$GIT_BACKUP|$GIT_BACKUP|g" "$ALIAS_FILE"
sed -i "s|\$ROOT|$ROOT|g" "$ALIAS_FILE"
echo "  ✔ Shell alias created at $ALIAS_FILE"

echo ""
echo "✅ Git separated successfully."
echo ""
echo "Next steps:"
echo "  1. Add this to your shell profile (.bashrc / .zshrc):"
echo "     source \"$ALIAS_FILE\""
echo ""
echo "  2. Use 'maicelium-git' instead of 'git' for workspace operations:"
echo "     maicelium-git status"
echo "     maicelium-git add -A && maicelium-git commit -m \"msg\""
echo "     maicelium-git push"
echo ""
echo "  3. Or use the /git_backup command from within the IDE."
