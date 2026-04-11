#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
_load_conventions "$ROOT"

# ── Parse arguments ──────────────────────────────────────────────────────────
NAME=""
LAYER_PATH=""
CLIENT=""
REPO_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client) CLIENT="$2"; shift 2 ;;
    --repo)   REPO_URL="$2"; shift 2 ;;
    -*)       echo "❌ Unknown flag '$1'"; exit 1 ;;
    *)
      if [ -z "$NAME" ]; then NAME="$1"
      elif [ -z "$LAYER_PATH" ]; then LAYER_PATH="$(realpath "$1" 2>/dev/null || echo "$1")"
      else echo "❌ Unexpected argument: $1"; exit 1
      fi
      shift ;;
  esac
done

if [ -z "$NAME" ] || [ -z "$LAYER_PATH" ]; then
  echo "Usage: add_mesh_layer.sh <name> <path> [--client <client>] [--repo <url>]"
  echo "  <name>      Identifier for this layer (e.g. acme-corp)"
  echo "  <path>      Local path to the mesh layer repo"
  echo "  --client    Client name for rule/skill prefixing (defaults to <name>)"
  echo "  --repo      Git remote URL (optional, for documentation)"
  exit 1
fi

[ -z "$CLIENT" ] && CLIENT="$NAME"

if [ ! -d "$LAYER_PATH" ]; then
  echo "❌ Path '$LAYER_PATH' does not exist."
  exit 1
fi

# ── Check for rules/skills content ───────────────────────────────────────────
if [ ! -d "$LAYER_PATH/rules" ] && [ ! -d "$LAYER_PATH/skills" ]; then
  echo "⚠️  Warning: '$LAYER_PATH' has no rules/ or skills/ directory."
fi

# ── Update WORKSPACE.md ──────────────────────────────────────────────────────
python3 - "$ROOT" "$NAME" "$LAYER_PATH" "$CLIENT" "$REPO_URL" <<'PYEOF'
import sys, os

root, name, path, client, repo = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
wf = os.path.join(root, "WORKSPACE.md")

import datetime
now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
if not os.path.exists(wf):
    content = "# Active workspace\n\nprojects: []\n\ncreated: {}\n".format(now)
else:
    with open(wf) as f:
        content = f.read()

# Build entry
entry_lines = [f"- name: {name}", f"  path: {path}", f"  client: {client}"]
if repo:
    entry_lines.append(f"  repo: {repo}")
entry = "\n".join(entry_lines)

# Check for duplicate within mesh_layers section only
in_layers = False
for line in content.splitlines():
    stripped = line.strip()
    if stripped == "mesh_layers:":
        in_layers = True
        continue
    if in_layers:
        if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
            break
        if stripped == f"- name: {name}":
            print(f"  ⚠️  Layer '{name}' already exists in WORKSPACE.md")
            sys.exit(0)

# Insert into mesh_layers section or create it
if "mesh_layers:" in content:
    # Find end of mesh_layers block and append there
    lines = content.splitlines()
    insert_at = None
    in_layers = False
    for i, line in enumerate(lines):
        if line.strip() == "mesh_layers:":
            in_layers = True
            continue
        if in_layers:
            if line and not line.startswith(' ') and not line.startswith('-') and line.strip().endswith(':'):
                insert_at = i
                break
    if insert_at is None:
        # mesh_layers is the last section
        content = content.rstrip() + "\n" + entry + "\n"
    else:
        lines.insert(insert_at, entry)
        content = "\n".join(lines) + "\n"
else:
    # Prepend mesh_layers before projects:
    if "projects:" in content:
        content = content.replace("projects:", f"mesh_layers:\n{entry}\n\nprojects:", 1)
    else:
        content = f"mesh_layers:\n{entry}\n\n" + content

with open(wf, "w") as f:
    f.write(content)
print(f"  ✔ WORKSPACE.md updated")
PYEOF

echo "✔ Mesh layer '$NAME' added → $LAYER_PATH (client: $CLIENT)"

# ── Sync symlinks ─────────────────────────────────────────────────────────────
echo "  → Running sync..."
bash "$ROOT/bin/sync_symlinks.sh" 2>&1 | grep -E "(✔|⚠️|✅|Layer)"
echo "  ✔ Sync complete"
