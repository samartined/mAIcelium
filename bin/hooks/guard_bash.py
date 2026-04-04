#!/usr/bin/env python3
"""PreToolUse hook: block dangerous Bash commands.

Reads Claude Code hook JSON from stdin. Outputs block decision or exits 0 (allow).
"""
import sys
import json
import re

def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cmd = data.get("tool_input", {}).get("command", "")
    if not cmd:
        sys.exit(0)

    # Normalise: collapse whitespace, lowercase for pattern matching
    norm = " ".join(cmd.lower().split())

    # ── Catastrophic deletion ────────────────────────────────────────────────────
    # Allow safe targets: node_modules, __pycache__, .cache, dist, build, tmp, .tmp
    if re.search(r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r", norm):
        if not re.search(r"(node_modules|__pycache__|\.cache|/dist|/build|/tmp|\.tmp)", norm):
            # Block rm -rf targeting root, home, or wildcard root paths
            if re.search(r"rm\s+-[a-z]*rf?\s+(/\s|/\*|~/|~\s|\$home)", norm):
                block("Blocked: rm -rf on root/home directory. This would destroy the filesystem.")

    # ── SQL destruction ──────────────────────────────────────────────────────────
    if re.search(r"(drop\s+(table|database)|truncate\s+table)", norm):
        block("Blocked: destructive SQL command (DROP/TRUNCATE). Verify intent before executing.")

    # ── Force push to protected branches ─────────────────────────────────────────
    if re.search(r"git\s+push\s+.*(-f|--force)", norm) and re.search(r"\b(main|master)\b", norm):
        block("Blocked: force push to main/master. This rewrites shared history.")

    # ── Dangerous disk operations ────────────────────────────────────────────────
    if re.search(r"(mkfs\.|\>\s*/dev/sd|dd\s+if=.*/dev/)", norm):
        block("Blocked: low-level disk operation (mkfs/dd). This could destroy disk data.")

    # ── Insecure permissions ─────────────────────────────────────────────────────
    if re.search(r"chmod\s+777", norm):
        block("Blocked: chmod 777 sets world-writable permissions. Use more restrictive permissions.")

    # All checks passed — allow silently
    sys.exit(0)

if __name__ == "__main__":
    main()
