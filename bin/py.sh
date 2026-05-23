#!/bin/sh
# Cross-platform Python launcher shim.
# Resolves the first available interpreter so .claude/settings.json
# does not have to embed conditional logic. Linux/macOS path.
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$@"
else
  echo "py.sh: no python3 or python found in PATH" >&2
  exit 127
fi
