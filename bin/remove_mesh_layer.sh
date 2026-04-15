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

# ── Remove materialized symlinks from mesh/ internal mirrors ─────────────────
# Any symlink under mesh/skills/_common, mesh/skills/_domains, mesh/rules/_domains
# that resolves into mesh/layers/<name>/ belongs to this layer and must go.
# mesh/skills/_clients/<client>/ and mesh/rules/_clients/<client>/ are fully
# owned by this client — remove them entirely if no real files remain.
python3 - "$ROOT" "$NAME" "$CLIENT" <<'PYEOF'
import os, sys, shutil

root, name, client = sys.argv[1], sys.argv[2], sys.argv[3]
layer_dir = os.path.join(root, "mesh", "layers", name)
layer_real = os.path.realpath(layer_dir) if os.path.exists(layer_dir) else None

removed = 0

# Scan _common, _domains, and rules/_domains for symlinks pointing into this layer
scan_dirs = [
    os.path.join(root, "mesh", "skills", "_common"),
    os.path.join(root, "mesh", "skills", "_domains"),
    os.path.join(root, "mesh", "rules", "_domains"),
]
for base in scan_dirs:
    if not os.path.isdir(base):
        continue
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for entry in list(dirnames) + filenames:
            p = os.path.join(dirpath, entry)
            if not os.path.islink(p):
                continue
            try:
                target = os.path.realpath(p)
            except OSError:
                continue
            if layer_real and target.startswith(layer_real + os.sep):
                os.remove(p)
                removed += 1

# _clients/<client>/ — remove symlinks that belong to this layer, then
# drop the whole dir if it's empty (pure layer ownership).
for kind in ("skills", "rules"):
    client_dir = os.path.join(root, "mesh", kind, "_clients", client)
    if not os.path.isdir(client_dir):
        continue
    for entry in list(os.listdir(client_dir)):
        p = os.path.join(client_dir, entry)
        if os.path.islink(p):
            try:
                target = os.path.realpath(p)
            except OSError:
                target = ""
            if not layer_real or target.startswith(layer_real + os.sep):
                os.remove(p)
                removed += 1
    if not os.listdir(client_dir):
        os.rmdir(client_dir)

# Finally, remove mesh/layers/<name> if it's a symlink (leave real dirs alone)
if os.path.islink(layer_dir):
    os.remove(layer_dir)
    removed += 1
    print(f"  ✔ mesh/layers/{name} symlink removed")
elif os.path.isdir(layer_dir):
    print(f"  ⚠️  mesh/layers/{name} is a real directory — left in place")

if removed:
    print(f"  ✔ {removed} mesh/ symlink(s) cleaned for layer '{name}'")
PYEOF

# ── Remove entry from WORKSPACE.md ───────────────────────────────────────────
python3 - "$ROOT" "$NAME" <<'PYEOF'
import sys, os

root, name = sys.argv[1], sys.argv[2]
wf = os.path.join(root, "WORKSPACE.md")

if not os.path.exists(wf):
    print("  ⏭ WORKSPACE.md does not exist, skipping")
    sys.exit(0)

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
