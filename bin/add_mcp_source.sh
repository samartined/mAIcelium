#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"

# ── Parse arguments ──────────────────────────────────────────────────────────
SRC_PATH=""
REPO_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_URL="$2"; shift 2 ;;
    -*)     echo "❌ Unknown flag '$1'"; exit 1 ;;
    *)
      if [ -z "$SRC_PATH" ]; then
        SRC_PATH="$(realpath "$1" 2>/dev/null || echo "$1")"
      else
        echo "❌ Unexpected argument: $1"; exit 1
      fi
      shift ;;
  esac
done

if [ -z "$SRC_PATH" ]; then
  echo "Usage: add_mcp_source.sh <path> [--repo <url>]"
  echo "  <path>   Local path to the external MCP definitions directory"
  echo "  --repo   Git remote URL (optional, documentation only)"
  exit 1
fi

if [ ! -d "$SRC_PATH" ]; then
  echo "❌ Path '$SRC_PATH' does not exist or is not a directory."
  exit 1
fi

# ── Update WORKSPACE.md ──────────────────────────────────────────────────────
python3 - "$ROOT" "$SRC_PATH" "$REPO_URL" <<'PYEOF'
import sys, os, datetime

root, path, repo = sys.argv[1], sys.argv[2], sys.argv[3]
wf = os.path.join(root, "WORKSPACE.md")

now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
if not os.path.exists(wf):
    content = "# Active workspace\n\nprojects: []\n\ncreated: {}\n".format(now)
else:
    with open(wf) as f:
        content = f.read()

# Build entry
entry_lines = ["mcp_source:", f"  path: {path}"]
if repo:
    entry_lines.append(f"  repo: {repo}")
entry = "\n".join(entry_lines)

lines = content.splitlines()
new_lines = []
i = 0
replaced = False

while i < len(lines):
    line = lines[i]
    if line.strip() == "mcp_source:":
        # Replace existing block: skip until next top-level key or blank line
        replaced = True
        new_lines.extend(entry.splitlines())
        i += 1
        while i < len(lines):
            nxt = lines[i]
            nxt_stripped = nxt.strip()
            if nxt and not nxt.startswith(' ') and not nxt.startswith('-') and nxt_stripped.endswith(':'):
                break
            if nxt_stripped == '' and i + 1 < len(lines):
                # Keep one blank between blocks
                new_lines.append(nxt)
                i += 1
                break
            i += 1
        continue
    new_lines.append(line)
    i += 1

if not replaced:
    # Insert mcp_source before projects: (so order is: mesh_layers → mcp_source → projects)
    final = []
    inserted = False
    for line in new_lines:
        if not inserted and line.strip() == "projects:":
            final.append(entry)
            final.append("")
            inserted = True
        final.append(line)
    if not inserted:
        # No projects: section — append at the end
        final = new_lines + ["", entry, ""]
    new_lines = final

output = "\n".join(new_lines)
if not output.endswith("\n"):
    output += "\n"

with open(wf, "w") as f:
    f.write(output)

print(f"  ✔ WORKSPACE.md updated (mcp_source: {path})")
PYEOF

echo "✔ MCP source registered → $SRC_PATH"

# ── Sync symlinks ─────────────────────────────────────────────────────────────
echo "  → Running sync..."
bash "$ROOT/bin/sync_symlinks.sh" 2>&1 | grep -E "(✔|⚠️|✅|MCP)"
echo "  ✔ Sync complete"
