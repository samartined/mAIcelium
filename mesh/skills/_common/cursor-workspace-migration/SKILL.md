---
name: cursor-workspace-migration
description: >-
  Migrate Cursor IDE chat history and agent transcripts when moving or renaming
  a project workspace to a different path. Use when the user wants to move,
  rename, or relocate a Cursor project folder without losing chats, composer
  history, or agent conversations.
---

# Cursor Workspace Migration

Migrates chat history and agent transcripts when moving a Cursor workspace to a different path.

## Problem

Cursor ties chats to the project's absolute path. Moving or renaming the folder causes chats to disappear because Cursor creates a new empty workspace. The data is not deleted — it becomes orphaned in internal storage.

## Chat Storage Architecture

Chats are stored in **two independent locations**:

| Data | Location | Contents |
|------|----------|----------|
| Composer/sidebar chats | `STATE_BASE/workspaceStorage/<hash>/state.vscdb` | Chat index (`composer.composerData`), layout, file history |
| Agent transcripts | `~/.cursor/projects/<workspace-slug>/agent-transcripts/<uuid>/` | Full message history for each Agent conversation (`.jsonl`) |

### Relationship Between Both Stores

- `state.vscdb` contains the chat **index** with `composerId` UUIDs
- `agent-transcripts` contains the actual **message content**, in folders named with the same UUID
- **Cursor resolves chats by transcript UUID**: if two workspaces share a transcript with the same UUID, Cursor displays new messages in both (mirror effect)

### Platform-Specific Base Paths (`STATE_BASE`)

| Platform | Path |
|----------|------|
| Linux (AppImage) | `~/.config/cursor/Cursor/User/` |
| Linux (alternative) | `~/.config/Cursor/User/` |
| macOS | `~/Library/Application Support/Cursor/User/` |
| Windows | `%APPDATA%\Cursor\User\` |

**Important on Linux**: check both paths (`~/.config/cursor/Cursor/` and `~/.config/Cursor/`). The AppImage typically uses the first variant.

### How Cursor Identifies Each Workspace

- **workspaceStorage hash**: `MD5(absolute_path + filesystem_salt)`
  - Linux: salt = inode number (`stat -c "%i" /path`)
  - macOS/Windows: salt = birthtime in milliseconds
- **projects folder slug**: path without leading `/`, separators replaced by `-` (`/home/user/dev/project` → `home-user-dev-project`)

## Migration Procedure

### Prerequisites

1. Source path (old) and destination path (new)
2. **Cursor completely closed** (SQLite DB cannot be modified while Cursor holds a lock)
3. `sqlite3` available on the system
4. `python3` available (for JSON manipulation)

### Step 1 — Identify Workspace Hashes

```bash
for base in ~/.config/cursor/Cursor/User ~/.config/Cursor/User \
            "$HOME/Library/Application Support/Cursor/User"; do
  if [ -d "$base/workspaceStorage" ]; then
    echo "STATE_BASE: $base"
    for dir in "$base/workspaceStorage"/*/; do
      if [ -f "$dir/workspace.json" ]; then
        echo "  $(basename $dir): $(cat "$dir/workspace.json")"
      fi
    done
  fi
done
```

Find the hashes containing the old and new paths in their `workspace.json`.

If the new workspace does not exist yet, open Cursor once with the new path and close it, or compute the hash manually:

```bash
INODE=$(stat -c "%i" /new/path)
NEW_HASH=$(echo -n "/new/path${INODE}" | md5sum | cut -d' ' -f1)
mkdir -p "$STATE_BASE/workspaceStorage/$NEW_HASH"
echo '{"folder":"file:///new/path"}' > "$STATE_BASE/workspaceStorage/$NEW_HASH/workspace.json"
```

### Step 2 — Copy state.vscdb and Update Paths

```bash
WS_DIR="$STATE_BASE/workspaceStorage"

cp "$WS_DIR/$NEW_HASH/state.vscdb" "$WS_DIR/$NEW_HASH/state.vscdb.pre-migration-backup"
cp "$WS_DIR/$OLD_HASH/state.vscdb" "$WS_DIR/$NEW_HASH/state.vscdb"
[ -d "$WS_DIR/$OLD_HASH/images" ] && cp -a "$WS_DIR/$OLD_HASH/images" "$WS_DIR/$NEW_HASH/"

sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" "
UPDATE ItemTable
SET value = REPLACE(value, '/old/path', '/new/path')
WHERE value LIKE '%/old/path%';
"
```

### Step 3 — Regenerate composerIds (CRITICAL)

Without this step, both workspaces share the same chat UUIDs and Cursor treats them as mirrors: new messages written in one workspace appear in the other.

```python
import json, sqlite3, uuid

db_path = "STATE_BASE/workspaceStorage/NEW_HASH/state.vscdb"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

composer_row = cursor.execute(
    "SELECT value FROM ItemTable WHERE key = 'composer.composerData'"
).fetchone()
data = json.loads(composer_row[0])
id_map = {c['composerId']: str(uuid.uuid4()) for c in data['allComposers']}

rows = cursor.execute("SELECT key, value FROM ItemTable").fetchall()
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
    cursor.execute("UPDATE ItemTable SET value = ? WHERE key = ?", (new_value, key))
for old_key, new_key, new_value in renames:
    cursor.execute("DELETE FROM ItemTable WHERE key = ?", (old_key,))
    cursor.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                   (new_key, new_value))

conn.commit()
conn.close()

with open("/tmp/cursor_id_map.json", "w") as f:
    json.dump(id_map, f)
```

### Step 4 — Copy and Rename Agent Transcripts

Transcripts must be copied to the new workspace **with the regenerated UUIDs**. The old UUIDs must also be removed from the source workspace to prevent the mirror effect.

```bash
PROJ_DIR="$HOME/.cursor/projects"
OLD_SLUG="<old-slug>"
NEW_SLUG="<new-slug>"

mkdir -p "$PROJ_DIR/$NEW_SLUG/agent-transcripts"

python3 << 'EOF'
import json, shutil, os

proj_dir = os.path.expanduser("~/.cursor/projects")
old_slug = "OLD_SLUG"
new_slug = "NEW_SLUG"

with open("/tmp/cursor_id_map.json") as f:
    id_map = json.load(f)

old_at = f"{proj_dir}/{old_slug}/agent-transcripts"
new_at = f"{proj_dir}/{new_slug}/agent-transcripts"
os.makedirs(new_at, exist_ok=True)

for old_id, new_id in id_map.items():
    src = f"{old_at}/{old_id}"
    if os.path.isdir(src):
        dst = f"{new_at}/{new_id}"
        shutil.copytree(src, dst, dirs_exist_ok=True)
        old_jsonl = f"{dst}/{old_id}.jsonl"
        new_jsonl = f"{dst}/{new_id}.jsonl"
        if os.path.exists(old_jsonl):
            os.rename(old_jsonl, new_jsonl)

# Copy transcripts not present in composerData
for entry in os.listdir(old_at) if os.path.isdir(old_at) else []:
    src = f"{old_at}/{entry}"
    if os.path.isdir(src) and entry not in id_map:
        new_id = str(__import__('uuid').uuid4())
        dst = f"{new_at}/{new_id}"
        shutil.copytree(src, dst)
        old_jsonl = f"{dst}/{entry}.jsonl"
        new_jsonl = f"{dst}/{new_id}.jsonl"
        if os.path.exists(old_jsonl):
            os.rename(old_jsonl, new_jsonl)
EOF
```

### Step 5 — Clean Duplicate Transcripts from Old Workspace

**This step prevents the mirror effect.** If the old workspace will still be used, remove the migrated transcripts from it:

```bash
python3 << 'EOF'
import json, shutil, os

proj_dir = os.path.expanduser("~/.cursor/projects")
old_slug = "OLD_SLUG"

with open("/tmp/cursor_id_map.json") as f:
    id_map = json.load(f)

old_at = f"{proj_dir}/{old_slug}/agent-transcripts"
for old_id in id_map.keys():
    target = f"{old_at}/{old_id}"
    if os.path.isdir(target):
        shutil.rmtree(target)
EOF
```

If the old workspace **will no longer be used**, delete its entire project directory:

```bash
rm -rf "$PROJ_DIR/$OLD_SLUG"
```

### Step 6 — Verify

```bash
# No remaining references to the old path
sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" \
  "SELECT COUNT(*) FROM ItemTable WHERE value LIKE '%/old/path%'"

# Count migrated chats
sqlite3 "$WS_DIR/$NEW_HASH/state.vscdb" \
  "SELECT value FROM ItemTable WHERE key = 'composer.composerData'" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('allComposers',[])),'chats')"

# No shared UUIDs between workspaces (must be empty)
comm -12 \
  <(ls "$PROJ_DIR/$OLD_SLUG/agent-transcripts/" 2>/dev/null | sort) \
  <(ls "$PROJ_DIR/$NEW_SLUG/agent-transcripts/" 2>/dev/null | sort)
```

### Step 7 — Open Cursor and Validate

Open Cursor at the new path. Confirm:
- Chats appear in the sidebar
- Messages load correctly
- Opening the old workspace does **not** show messages from the new one

## Automated Script

Use the [migrate-template.sh](migrate-template.sh) template to run all steps automatically:

```bash
.cursor/skills/cursor-workspace-migration/migrate-template.sh /old/path /new/path --clean-old
```

## Alternative Tool: cursor-helper

If Rust/cargo is available:

```bash
cargo install cursor-helper
cursor-helper rename /old/path /new/path
```

**Linux limitation**: requires filesystem birthtime support. If it fails with `creation time is not available`, use the manual procedure from this skill.

## Common Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| Chats missing in new workspace | `state.vscdb` not copied | Step 2 |
| New messages appear in both workspaces (mirror) | Duplicate UUIDs in agent-transcripts | Steps 3 + 4 + 5 |
| `state.vscdb` cannot be modified | Cursor is open | Close Cursor completely |
| cursor-helper fails on Linux | No birthtime support | Use manual procedure |
| New workspace hash not found | Cursor hasn't opened the new path | Open Cursor once or compute hash manually |
