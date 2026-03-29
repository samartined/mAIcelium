#!/usr/bin/env bash
# PreToolUse hook: block dangerous Bash commands.
# Reads Claude Code hook JSON from stdin. Outputs block decision or exits 0 (allow).
set -euo pipefail

# Fail-open if jq is missing
if ! command -v jq &>/dev/null; then
  exit 0
fi

CMD=$(jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# Normalise: collapse whitespace, lowercase for pattern matching
NORM=$(echo "$CMD" | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' ' ')

block() {
  local reason="$1"
  cat <<JSON
{"decision":"block","reason":"$reason"}
JSON
  exit 0
}

# ── Catastrophic deletion ────────────────────────────────────────────────────
# Allow safe targets: node_modules, __pycache__, .cache, dist, build, tmp, .tmp
if echo "$NORM" | grep -qE 'rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r'; then
  if ! echo "$NORM" | grep -qE '(node_modules|__pycache__|\.cache|/dist|/build|/tmp|\.tmp)'; then
    # Block rm -rf targeting root, home, or wildcard root paths
    if echo "$NORM" | grep -qE 'rm\s+-[a-z]*rf?\s+(/\s|/\*|~/|~\s|\$home)'; then
      block "Blocked: rm -rf on root/home directory. This would destroy the filesystem."
    fi
  fi
fi

# ── SQL destruction ──────────────────────────────────────────────────────────
if echo "$NORM" | grep -qE '(drop\s+(table|database)|truncate\s+table)'; then
  block "Blocked: destructive SQL command (DROP/TRUNCATE). Verify intent before executing."
fi

# ── Force push to protected branches ─────────────────────────────────────────
if echo "$NORM" | grep -qE 'git\s+push\s+.*(-f|--force)' && echo "$NORM" | grep -qE '\b(main|master)\b'; then
  block "Blocked: force push to main/master. This rewrites shared history."
fi

# ── Dangerous disk operations ────────────────────────────────────────────────
if echo "$NORM" | grep -qE '(mkfs\.|>\s*/dev/sd|dd\s+if=.*/dev/)'; then
  block "Blocked: low-level disk operation (mkfs/dd). This could destroy disk data."
fi

# ── Insecure permissions ─────────────────────────────────────────────────────
if echo "$NORM" | grep -qE 'chmod\s+777'; then
  block "Blocked: chmod 777 sets world-writable permissions. Use more restrictive permissions."
fi

# All checks passed — allow silently
exit 0
