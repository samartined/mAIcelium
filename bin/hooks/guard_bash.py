#!/usr/bin/env python3
"""PreToolUse hook: block dangerous Bash commands.

Reads Claude Code hook JSON from stdin. Outputs block decision or exits 0
(allow). Fail-open if stdin is malformed; logged to .claude/hook-failures.log
for diagnosis.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone


def _get_root():
    """Resolve workspace root. Allow override via MAICELIUM_ROOT for tests."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    # bin/hooks/guard_bash.py -> root is 2 levels up from the file
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _log_failure(reason):
    """Append a line to .claude/hook-failures.log."""
    root = _get_root()
    log_path = os.path.join(root, ".claude", "hook-failures.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{ts} guard_bash {reason}\n")
    except OSError:
        pass


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        _log_failure(f"stdin-parse-error: {e}")
        sys.exit(0)  # Fail-open on malformed input

    if not isinstance(data, dict):
        _log_failure("stdin-not-object")
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)

    cmd = tool_input.get("command", "")
    if not isinstance(cmd, str) or not cmd:
        sys.exit(0)

    # Normalise: collapse whitespace, lowercase for pattern matching.
    # Append a trailing space so patterns anchored on a following whitespace
    # (e.g. "/ " or "~ ") still match when the command ends at the target.
    norm = " ".join(cmd.lower().split()) + " "

    # Catastrophic deletion (rm -rf on / ~ etc.)
    if re.search(r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r", norm):
        if not re.search(
            r"(node_modules|__pycache__|\.cache|/dist|/build|/tmp|\.tmp)", norm
        ):
            if re.search(
                r"rm\s+-[a-z]*rf?\s+(/\s|/\*|~/|~\s|\$home)", norm
            ):
                _block(
                    "Blocked: rm -rf on root/home directory. "
                    "This would destroy the filesystem."
                )

    # SQL destruction
    if re.search(r"(drop\s+(table|database)|truncate\s+table)", norm):
        _block(
            "Blocked: destructive SQL command (DROP/TRUNCATE). "
            "Verify intent before executing."
        )

    # Force push to main/master
    if re.search(r"git\s+push\s+.*(-f|--force)", norm) and re.search(
        r"\b(main|master)\b", norm
    ):
        _block(
            "Blocked: force push to main/master. "
            "This rewrites shared history."
        )

    # Dangerous disk ops
    if re.search(r"(mkfs\.|>\s*/dev/sd|dd\s+if=.*/dev/)", norm):
        _block(
            "Blocked: low-level disk operation (mkfs/dd). "
            "This could destroy disk data."
        )

    # chmod 777
    if re.search(r"chmod\s+777", norm):
        _block(
            "Blocked: chmod 777 sets world-writable permissions. "
            "Use more restrictive permissions."
        )

    # Terraform preflight enforcement
    if re.search(r"(^|[;&|\s])(terraform|tf)(\s|$)", norm):
        if re.search(
            r"(terraform|tf)\s+"
            r"(init|plan|apply|destroy|validate|import|state|"
            r"workspace\s+select)\b",
            norm,
        ):
            if not re.search(r"tfswitch\b", norm):
                _block(
                    "Blocked: Terraform command requires tfswitch preflight "
                    "in the same command. Run 'tfswitch' before Terraform."
                )

    sys.exit(0)


if __name__ == "__main__":
    main()
