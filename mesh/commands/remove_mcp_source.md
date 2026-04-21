---
description: >-
  Unmount the registered MCP source. The external directory is never touched.
---
# Command: /remove_mcp_source

## Purpose
Unregister the current MCP source from the workspace. The `mesh/mcp` symlink is
removed, the `mcp_source:` block is stripped from WORKSPACE.md, and the three
generated MCP configs are refreshed with an empty `mcpServers`. The external
directory is never touched.

## Instructions

Run:

```bash
cd $WORKSPACE_ROOT && bin/remove_mcp_source.sh
```

Then output the script's response **verbatim** as your only reply. No extra text.

## Notes
- Safe to run when no source is registered (no-op with informational message).
- Remounting later restores identical state by running `/add_mcp_source <path>`.

## Safety
NEVER remove contents of the external MCP directory itself — only the symlink at
`mesh/mcp/` and the registry entry in WORKSPACE.md.
