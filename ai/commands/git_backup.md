# Command: /git_backup

## Purpose
Stage, commit, and push all changes in the mAIcelium workspace to GitHub
using the separated git directory (if configured).

## Prerequisites
The `.git` directory must have been separated using `bin/separate_git.sh`.
If `.git` still exists in the workspace root, use regular git commands instead.

## Instructions

The user may optionally provide a commit message, e.g. `/git_backup add new terraform skill`.
If no message is provided, auto-generate one from the changes.

### Detect git configuration

First, determine which git mode is active:

```bash
if [ -d "$WORKSPACE_ROOT/.git" ]; then
  # Normal mode — .git is in the workspace
  GIT_CMD="git"
else
  # Separated mode — .git is in the backup directory
  BACKUP_DIR="${WORKSPACE_ROOT}-git-backup"
  GIT_CMD="git --git-dir=$BACKUP_DIR/.git --work-tree=$WORKSPACE_ROOT"
fi
```

> **IMPORTANT:** In separated mode, every `git` command MUST include both
> `--git-dir` and `--work-tree` flags. Never run bare `git` commands.

### Step 1: Check status

Run: `$GIT_CMD status --short`

If the output is empty, respond: `✅ Nothing to push — workspace is clean.`

### Step 2: Review changes

Run: `$GIT_CMD diff --stat`

Use the output to understand what changed (helps auto-generate a commit message).

### Step 3: Stage all changes

Run: `$GIT_CMD add -A`

### Step 4: Commit

If the user provided a message, use it. Otherwise, generate a concise message
from the changes (e.g. "update terraform skill, add push-backup command").

Run: `$GIT_CMD commit -m "<message>"`

### Step 5: Push

Run: `$GIT_CMD push origin main`

If push fails, show the error and stop. Do NOT retry automatically.

### Step 6: Respond

Output **only** this: `✅ Pushed to **origin/main** — <short hash> <message>`
