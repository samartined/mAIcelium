#!/bin/bash
#
# Cursor Workspace Chat Migration
# Migrates chats and agent transcripts when moving a workspace to a new path.
# Regenerates UUIDs to prevent the mirror effect between workspaces.
#
# USAGE: ./migrate-template.sh /old/path /new/path [--keep-old | --clean-old]
#
#   --keep-old   Keep transcripts in the old workspace (default)
#   --clean-old  Remove migrated transcripts from the old workspace (prevents mirror)
#
set -euo pipefail

OLD_PATH="${1:?Usage: $0 /old/path /new/path [--keep-old | --clean-old]}"
NEW_PATH="${2:?Usage: $0 /old/path /new/path [--keep-old | --clean-old]}"
MODE="${3:---keep-old}"

OLD_PATH=$(realpath "$OLD_PATH" 2>/dev/null || echo "$OLD_PATH")
NEW_PATH=$(realpath "$NEW_PATH" 2>/dev/null || echo "$NEW_PATH")

detect_state_base() {
    local candidates=(
        "$HOME/.config/cursor/Cursor/User"
        "$HOME/.config/Cursor/User"
        "$HOME/Library/Application Support/Cursor/User"
    )
    for base in "${candidates[@]}"; do
        if [ -d "$base/workspaceStorage" ]; then
            echo "$base"
            return 0
        fi
    done
    echo "ERROR: Cursor workspaceStorage directory not found" >&2
    return 1
}

find_workspace_hash() {
    local target_path="$1"
    local ws_dir="$2/workspaceStorage"
    for dir in "$ws_dir"/*/; do
        if [ -f "$dir/workspace.json" ]; then
            if grep -q "$(echo "$target_path" | sed 's/[\/&]/\\&/g')" "$dir/workspace.json" 2>/dev/null; then
                basename "$dir"
                return 0
            fi
        fi
    done
    return 1
}

path_to_slug() {
    echo "$1" | sed 's|^/||; s|/|-|g'
}

echo "=== Cursor Workspace Chat Migration ==="
echo "Source:  $OLD_PATH"
echo "Target:  $NEW_PATH"
echo "Mode:    $MODE"
echo ""

if pgrep -f "[Cc]ursor" > /dev/null 2>&1; then
    echo "WARNING: Cursor appears to be running."
    echo "The DB cannot be modified while Cursor holds a lock."
    read -p "Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted. Close Cursor and retry."
        exit 1
    fi
fi

STATE_BASE=$(detect_state_base)
echo "State base: $STATE_BASE"

echo ""
echo "[1/7] Identifying workspace hashes..."

OLD_HASH=$(find_workspace_hash "$OLD_PATH" "$STATE_BASE") || {
    echo "ERROR: workspaceStorage not found for: $OLD_PATH"
    echo "Make sure Cursor has opened this path at least once."
    exit 1
}
echo "  Source: $OLD_HASH"

NEW_HASH=$(find_workspace_hash "$NEW_PATH" "$STATE_BASE") || {
    echo "  Target not found. Creating..."
    if [ "$(uname)" = "Linux" ]; then
        INODE=$(stat -c "%i" "$NEW_PATH")
        NEW_HASH=$(echo -n "${NEW_PATH}${INODE}" | md5sum | cut -d' ' -f1)
    elif [ "$(uname)" = "Darwin" ]; then
        BTIME=$(stat -f "%.3FB" "$NEW_PATH" | tr -d '.')
        NEW_HASH=$(echo -n "${NEW_PATH}${BTIME}" | md5 | cut -d' ' -f1)
    else
        echo "ERROR: Unsupported platform for automatic hash computation."
        exit 1
    fi
    mkdir -p "$STATE_BASE/workspaceStorage/$NEW_HASH"
    echo "{\"folder\":\"file://$NEW_PATH\"}" > "$STATE_BASE/workspaceStorage/$NEW_HASH/workspace.json"
}
echo "  Target: $NEW_HASH"

WS_DIR="$STATE_BASE/workspaceStorage"
PROJ_DIR="$HOME/.cursor/projects"
OLD_SLUG=$(path_to_slug "$OLD_PATH")
NEW_SLUG=$(path_to_slug "$NEW_PATH")

echo ""
echo "[2/7] Backing up target state.vscdb..."
if [ -f "$WS_DIR/$NEW_HASH/state.vscdb" ]; then
    cp "$WS_DIR/$NEW_HASH/state.vscdb" \
       "$WS_DIR/$NEW_HASH/state.vscdb.pre-migration-$(date +%Y%m%d%H%M%S)"
    echo "  Backup created."
else
    echo "  No existing state.vscdb in target."
fi

echo ""
echo "[3/7] Copying state.vscdb and updating paths..."
cp "$WS_DIR/$OLD_HASH/state.vscdb" "$WS_DIR/$NEW_HASH/state.vscdb"
for subdir in images; do
    if [ -d "$WS_DIR/$OLD_HASH/$subdir" ]; then
        cp -a "$WS_DIR/$OLD_HASH/$subdir" "$WS_DIR/$NEW_HASH/"
        echo "  Copied $subdir directory."
    fi
done

OLD_PATH_ESC=$(echo "$OLD_PATH" | sed "s/'/''/g")
NEW_PATH_ESC=$(echo "$NEW_PATH" | sed "s/'/''/g")
sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" "
UPDATE ItemTable
SET value = REPLACE(value, '$OLD_PATH_ESC', '$NEW_PATH_ESC')
WHERE value LIKE '%$OLD_PATH_ESC%';
"
echo "  state.vscdb copied and paths updated."

echo ""
echo "[4/7] Regenerating composerIds..."
python3 << PYEOF
import json, sqlite3, uuid

db_path = "$WS_DIR/$NEW_HASH/state.vscdb"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

row = cur.execute(
    "SELECT value FROM ItemTable WHERE key = 'composer.composerData'"
).fetchone()
if not row:
    print("  No composerData found. Skipping.")
    conn.close()
    exit(0)

data = json.loads(row[0])
id_map = {c['composerId']: str(uuid.uuid4()) for c in data.get('allComposers', [])}

rows = cur.execute("SELECT key, value FROM ItemTable").fetchall()
updates, renames = [], []

for key, value in rows:
    new_key, new_value = key, value
    for old_id, new_id in id_map.items():
        new_key = new_key.replace(old_id, new_id)
        new_value = new_value.replace(old_id, new_id)
    if new_key != key:
        renames.append((key, new_key, new_value))
    elif new_value != value:
        updates.append((new_value, key))

for new_value, key in updates:
    cur.execute("UPDATE ItemTable SET value = ? WHERE key = ?", (new_value, key))
for old_key, new_key, new_value in renames:
    cur.execute("DELETE FROM ItemTable WHERE key = ?", (old_key,))
    cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                (new_key, new_value))

conn.commit()
conn.close()

with open("/tmp/cursor_id_map.json", "w") as f:
    json.dump(id_map, f)

print(f"  {len(id_map)} composerIds regenerated.")
print(f"  {len(updates)} values updated, {len(renames)} keys renamed.")
PYEOF

echo ""
echo "[5/7] Copying agent transcripts with new UUIDs..."
python3 << PYEOF
import json, shutil, os

proj_dir = os.path.expanduser("~/.cursor/projects")
old_slug = "$OLD_SLUG"
new_slug = "$NEW_SLUG"

with open("/tmp/cursor_id_map.json") as f:
    id_map = json.load(f)

old_at = f"{proj_dir}/{old_slug}/agent-transcripts"
new_at = f"{proj_dir}/{new_slug}/agent-transcripts"
os.makedirs(new_at, exist_ok=True)

copied = 0
for old_id, new_id in id_map.items():
    src = f"{old_at}/{old_id}"
    if os.path.isdir(src):
        dst = f"{new_at}/{new_id}"
        shutil.copytree(src, dst, dirs_exist_ok=True)
        old_jsonl = f"{dst}/{old_id}.jsonl"
        new_jsonl = f"{dst}/{new_id}.jsonl"
        if os.path.exists(old_jsonl):
            os.rename(old_jsonl, new_jsonl)
        copied += 1

# Copy transcripts not present in composerData
for entry in os.listdir(old_at) if os.path.isdir(old_at) else []:
    src = f"{old_at}/{entry}"
    dst_existing = f"{new_at}/{entry}"
    if os.path.isdir(src) and entry not in id_map and not os.path.exists(dst_existing):
        new_id = str(__import__('uuid').uuid4())
        dst = f"{new_at}/{new_id}"
        shutil.copytree(src, dst)
        old_jsonl = f"{dst}/{entry}.jsonl"
        new_jsonl = f"{dst}/{new_id}.jsonl"
        if os.path.exists(old_jsonl):
            os.rename(old_jsonl, new_jsonl)
        copied += 1

print(f"  {copied} transcripts copied with new UUIDs.")
PYEOF

echo ""
echo "[6/7] Cleaning old workspace..."
if [ "$MODE" = "--clean-old" ]; then
    python3 << PYEOF
import json, shutil, os

proj_dir = os.path.expanduser("~/.cursor/projects")
old_slug = "$OLD_SLUG"

with open("/tmp/cursor_id_map.json") as f:
    id_map = json.load(f)

old_at = f"{proj_dir}/{old_slug}/agent-transcripts"
removed = 0
for old_id in id_map.keys():
    target = f"{old_at}/{old_id}"
    if os.path.isdir(target):
        shutil.rmtree(target)
        removed += 1

print(f"  {removed} transcripts removed from old workspace.")
PYEOF
else
    echo "  Mode --keep-old: old workspace transcripts unchanged."
    echo "  NOTE: If both workspaces are used simultaneously, migrated chats"
    echo "  may show the mirror effect. Use --clean-old to prevent it."
fi

echo ""
echo "[7/7] Verification..."
REMAINING=$(sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" \
    "SELECT COUNT(*) FROM ItemTable WHERE value LIKE '%$OLD_PATH_ESC%'" 2>/dev/null)
echo "  References to old path: $REMAINING"

CHAT_COUNT=$(sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" \
    "SELECT value FROM ItemTable WHERE key = 'composer.composerData'" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('allComposers',[])))" 2>/dev/null \
    || echo "N/A")
echo "  Composer chats: $CHAT_COUNT"

TRANSCRIPT_COUNT=$(ls "$PROJ_DIR/$NEW_SLUG/agent-transcripts/" 2>/dev/null | wc -l)
echo "  Agent transcripts: $TRANSCRIPT_COUNT"

SHARED=$(comm -12 \
    <(ls "$PROJ_DIR/$OLD_SLUG/agent-transcripts/" 2>/dev/null | sort) \
    <(ls "$PROJ_DIR/$NEW_SLUG/agent-transcripts/" 2>/dev/null | sort) \
    | wc -l)
echo "  Shared UUIDs between workspaces: $SHARED (should be 0)"

rm -f /tmp/cursor_id_map.json

echo ""
echo "=== Migration complete ==="
echo "Open Cursor at: $NEW_PATH"
if [ "$SHARED" -gt 0 ]; then
    echo ""
    echo "WARNING: $SHARED shared UUIDs found. Run with --clean-old"
    echo "to remove duplicates from the old workspace and prevent the mirror effect."
fi
