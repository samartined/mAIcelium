---
description: >-
  Register an external directory as the MCP definitions source for the workspace.
---
# Command: /add_mcp_source

## Purpose
Register an external directory as the pluggable MCP source. The workspace mounts
it at `mesh/mcp/` via a symlink, and `sync_symlinks.sh` generates `.mcp.json`,
`.cursor/mcp.json`, and `.agents/mcp.json` from its `*.json` files. The external
directory is never tracked by this workspace's git.

## Instructions

The user provides an absolute path (and optionally a git remote URL for documentation).

Run:

```bash
cd $WORKSPACE_ROOT && bin/add_mcp_source.sh <absolute_path> [--repo <url>]
```

Then output the script's response **verbatim** as your only reply. No extra text.

## Notes
- If a different `mcp_source:` is already registered, it is replaced silently.
- Only one MCP source can be registered per workspace.
- The same external directory can be mounted in multiple workspaces simultaneously.

## Example
```
User: /add_mcp_source /Users/edgar/Dev/mAIcelium-mcp
→ runs: bin/add_mcp_source.sh /Users/edgar/Dev/mAIcelium-mcp
→ output includes: ✔ MCP source mounted → /Users/edgar/Dev/mAIcelium-mcp
```
