#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"

NAME="$1"

if [ -z "$NAME" ]; then
  echo "Usage: remove_mesh_layer.sh <name>"
  echo ""
  echo "Registered layers:"
  _load_mesh_layers "$ROOT" | python3 -c '
import json, sys
layers = json.load(sys.stdin)
if not layers:
    print("  (none)")
for l in layers:
    print("  - " + l["name"] + "  ->  " + l.get("path", "?"))
'
  exit 1
fi

# ── Resolve layer info from WORKSPACE.md ─────────────────────────────────────
LAYER_INFO="$(_load_mesh_layers "$ROOT" | python3 -c "
import json, sys
layers = json.load(sys.stdin)
for l in layers:
    if l['name'] == '$NAME':
        print(l.get('client', l['name']))
        print(l.get('path', ''))
        sys.exit(0)
sys.exit(1)
" 2>/dev/null)" || {
  echo "❌ Layer '$NAME' not found in WORKSPACE.md."
  exit 1
}

CLIENT=$(echo "$LAYER_INFO" | sed -n '1p')
LAYER_PATH=$(echo "$LAYER_INFO" | sed -n '2p')

echo "Removing layer '$NAME' (client: $CLIENT, path: $LAYER_PATH)"

# ── Remove client--* symlinks from .cursor/rules/ ────────────────────────────
REMOVED=0
for link in "$ROOT"/.cursor/rules/${CLIENT}--*; do
  [ -L "$link" ] || continue
  rm "$link"
  REMOVED=$((REMOVED + 1))
done
[ "$REMOVED" -gt 0 ] && echo "  ✔ $REMOVED rule symlink(s) removed from .cursor/rules/"

# ── Remove client--* symlinks from .agents/rules/ ────────────────────────────
REMOVED=0
for link in "$ROOT"/.agents/rules/${CLIENT}--*; do
  [ -L "$link" ] || continue
  rm "$link"
  REMOVED=$((REMOVED + 1))
done
[ "$REMOVED" -gt 0 ] && echo "  ✔ $REMOVED rule symlink(s) removed from .agents/rules/"

# ── Remove client--* symlinks from .cursor/skills-cursor/ ────────────────────
REMOVED=0
for link in "$ROOT"/.cursor/skills-cursor/${CLIENT}--*; do
  [ -L "$link" ] || continue
  rm "$link"
  REMOVED=$((REMOVED + 1))
done
[ "$REMOVED" -gt 0 ] && echo "  ✔ $REMOVED skill symlink(s) removed from .cursor/skills-cursor/"

# ── Remove client--* symlinks from .agents/skills/ ───────────────────────────
REMOVED=0
for link in "$ROOT"/.agents/skills/${CLIENT}--*; do
  [ -L "$link" ] || continue
  rm "$link"
  REMOVED=$((REMOVED + 1))
done
[ "$REMOVED" -gt 0 ] && echo "  ✔ $REMOVED skill symlink(s) removed from .agents/skills/"

# ── Remove entry from WORKSPACE.md ───────────────────────────────────────────
python3 - "$ROOT" "$NAME" <<'PYEOF'
import sys, os

root, name = sys.argv[1], sys.argv[2]
wf = os.path.join(root, "WORKSPACE.md")

with open(wf) as f:
    lines = f.readlines()

out = []
skip = False
in_layers = False

for line in lines:
    stripped = line.strip()

    if stripped == "mesh_layers:":
        in_layers = True
        out.append(line)
        continue

    if in_layers:
        # Detect end of mesh_layers section
        if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
            in_layers = False
            skip = False
            out.append(line)
            continue

        if stripped == f"- name: {name}":
            skip = True
            continue

        if skip and line.startswith("  "):
            continue
        else:
            skip = False

    out.append(line)

with open(wf, "w") as f:
    f.writelines(out)

print("  ✔ WORKSPACE.md updated")
PYEOF

echo "✔ Layer '$NAME' removed from workspace (repo at '$LAYER_PATH' untouched)"

# ── Regenerate Claude Code project context ────────────────────────────────────
_regenerate_claude_context "$ROOT"
echo "  ✔ Claude project context updated"
