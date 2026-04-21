#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"

# ── Resolve current source (for user-facing message) ─────────────────────────
CURRENT="$(_load_mcp_source "$ROOT")"
if [ -z "$CURRENT" ]; then
  echo "ℹ️  No MCP source is registered in WORKSPACE.md."
else
  CURRENT_PATH="$(echo "$CURRENT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("path",""))')"
  echo "Removing MCP source (path: $CURRENT_PATH)"
fi

# ── Remove the mesh/mcp symlink if present ───────────────────────────────────
MCP_LINK="$ROOT/mesh/mcp"
if [ -L "$MCP_LINK" ]; then
  rm "$MCP_LINK"
  echo "  ✔ mesh/mcp symlink removed"
elif [ -d "$MCP_LINK" ]; then
  echo "  ⚠️  mesh/mcp is a real directory — left untouched"
fi

# ── Strip mcp_source: block from WORKSPACE.md ────────────────────────────────
python3 - "$ROOT" <<'PYEOF'
import sys, os

root = sys.argv[1]
wf = os.path.join(root, "WORKSPACE.md")

if not os.path.exists(wf):
    print("  ⏭ WORKSPACE.md does not exist, skipping")
    sys.exit(0)

with open(wf) as f:
    lines = f.readlines()

out = []
in_block = False

for line in lines:
    stripped = line.strip()

    if stripped == "mcp_source:":
        in_block = True
        continue

    if in_block:
        # End of block: new top-level key
        if line and not line.startswith(' ') and not line.startswith('-') and stripped.endswith(':'):
            in_block = False
            out.append(line)
            continue
        # Skip indented lines inside the block
        if line.startswith(' ') or not line.strip():
            # Drop blank-line companion only if the NEXT non-blank is outside the block
            if not line.strip():
                in_block = False
            continue

    out.append(line)

with open(wf, "w") as f:
    f.writelines(out)

print("  ✔ WORKSPACE.md updated")
PYEOF

# ── Regenerate generated configs (.mcp.json, etc.) ───────────────────────────
echo "  → Running sync to regenerate IDE configs..."
bash "$ROOT/bin/sync_symlinks.sh" 2>&1 | grep -E "(✔|⚠️|✅|MCP)"
echo "✔ MCP source removed (external directory left untouched)"
