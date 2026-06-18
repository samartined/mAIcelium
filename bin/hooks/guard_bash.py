#!/usr/bin/env python3
"""PreToolUse hook: best-effort defense-in-depth against dangerous Bash commands.

IMPORTANT — HONEST FRAMING
--------------------------
This hook is a *speed-bump*, not a security boundary. It performs regex
matching over the raw command string as Claude Code passes it to Bash.

It is INHERENTLY BYPASSABLE because:
  - Shell expansion happens after this check (environment variables, command
    substitution, process substitution, eval, base64 decoding, etc.).
  - Quoting styles can be chosen to defeat any literal regex.
  - Operand splitting across cd/subshells is invisible here (e.g.
    ``cd /etc && rm -rf foo`` is a known gap, documented in the tests).
  - A malicious user could construct an infinite number of equivalent encodings.

The hook FAILS OPEN by design (logged to .claude/hook-failures.log):
  - If stdin is malformed, the hook exits 0 without blocking.
  - If an unexpected exception occurs, the hook exits 0 without blocking.
  Real security boundaries are:
    1. Workspace write-scope enforcement via guard_write.py
    2. Human review of agent-proposed commands
    3. Principle of least privilege on the OS side

COVERED (cheap, false-positive-free literal cases)
---------------------------------------------------
  * rm -rf / rm -fr on protected root paths: /, /etc, /home, /usr, /var,
    /bin, /lib, /lib64, /boot, /root, /sys, /proc, /dev, /opt, /srv,
    /sbin (and exact-match subpaths of /home)
  * rm -rf on bare cwd/parent/wildcard operands: . .. ./ ../ * ./*
  * rm -rf on ~ / ~/... / $HOME
  * Destructive SQL (DROP TABLE, TRUNCATE)
  * git push --force to main/master
  * Low-level disk ops (mkfs, dd)
  * chmod 777
  * Terraform without tfswitch preflight

DOCUMENTED GAPS (not blocked — known best-effort limit)
-------------------------------------------------------
  * T=/etc; rm -rf $T          (variable indirection)
  * rm -rf $(echo /etc)        (command substitution)
  * cd /etc && rm -rf foo      (cwd tracking)
  * echo /etc | xargs rm -rf   (piped operands)
  * find /etc -delete           (non-rm deletion)
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

# Protected filesystem roots.  Absolute paths that, if passed to rm -rf,
# would likely cause catastrophic data loss.  /home is included here because
# ``rm -rf /home`` would destroy all user home directories; individual user
# subdirectories (e.g. /home/user) are handled by the subpath branch.
_PROTECTED_ROOTS = frozenset(
    [
        "/",
        "/etc",
        "/home",
        "/usr",
        "/var",
        "/bin",
        "/lib",
        "/lib64",
        "/boot",
        "/root",
        "/sys",
        "/proc",
        "/dev",
        "/opt",
        "/srv",
        "/sbin",
    ]
)

# Build an alternation of protected root prefixes for the regex.
# Each root is followed by either end-of-operand (quote/space/EOL) or "/",
# so that /tmp never matches (it is not in the set) but /etc and /etc/foo do.
_PROT_PATTERN = "|".join(
    re.escape(r) for r in sorted(_PROTECTED_ROOTS, key=len, reverse=True)
)

# Matches rm with recursive+force flags in either order, with optional extra
# single-letter flags between them, and an optional -- separator.
# Normalisation below collapses runs of spaces so \s+ catches single space.
_RM_FLAGS = r"rm\s+-[a-z]*r[a-z]*f[a-z]*|-[a-z]*f[a-z]*r[a-z]*"
# Full rm -rf/-fr expression:
_RM_RF = rf"rm\s+(?:-[a-z]*[rf][a-z]*\s+)*"

# The complete rm -rf guard (assembled at module load; not inside a loop to
# avoid ReDoS — all alternations are linear prefix-anchored strings).
#
# An operand is captured after optional quoting and optional "--" separator.
# The lookahead (?=[\s"'$]|$) ensures we match only at the END of the operand
# token, which prevents matching subpaths of non-protected directories
# (e.g. "rm -rf ./build" must NOT match even though it starts with ".").
#
# Operand classes:
#  A) protected absolute root (exact or with subpath)
#  B) bare relative dangerous operands: . .. ./ ../ * ./*
#  C) home shortcuts: ~ ~/ $home
_RM_RF_BLOCK = re.compile(
    r"""
    rm \s+                        # rm command
    (?:                           # optional flags block (e.g. -rf -- or -fr)
      -[a-z]*[rf][a-z]* \s+
    ){1,4}
    (?:--\s+)?                    # optional -- separator
    (?P<q>['"])?                  # optional opening quote
    (?:                           # operand alternatives
      # A) protected absolute root: exact or /subpath
      (?:""" + _PROT_PATTERN + r""")(?:/[^\s"']*)?
      |
      # B) bare relative dangerous operands (whole operand only)
      \.\.?/?
      |
      # C) wildcards
      \./?\*?(?!\w)
      |
      \*
      |
      # D) home shortcuts
      ~(?:/[^\s"']*)?
      |
      \$home(?:/[^\s"']*)?
    )
    (?P=q)?                       # matching closing quote (back-reference)
    (?=\s|"|'|$)                  # end of operand token
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Safe-operand allowlist — if the rm -rf operand matches one of these the
# block is waived.  Checked against the full normalised command string.
_RM_SAFE_OPERANDS = re.compile(
    r"rm\s+-[a-z]*[rf][a-z]*\s+(?:--\s+)?"
    r"(?:"
    r"node_modules"
    r"|__pycache__"
    r"|\.cache"
    r"|(?:\./)?(dist|build|target|out|coverage)"
    r"|/tmp/"
    r")",
    re.IGNORECASE,
)


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
    sys.exit(0)  # fail-open by design (see module docstring)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        _log_failure(f"stdin-parse-error: {e}")
        sys.exit(0)  # fail-open by design (see module docstring)

    if not isinstance(data, dict):
        _log_failure("stdin-not-object")
        sys.exit(0)  # fail-open by design (see module docstring)

    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)  # fail-open by design (see module docstring)

    cmd = tool_input.get("command", "")
    if not isinstance(cmd, str) or not cmd:
        sys.exit(0)  # fail-open by design (see module docstring)

    # Normalise: collapse whitespace, lowercase for pattern matching.
    # Append a trailing space so patterns anchored on a following whitespace
    # (e.g. "/ " or "~ ") still match when the command ends at the target.
    norm = " ".join(cmd.lower().split()) + " "

    # -----------------------------------------------------------------------
    # Catastrophic deletion guard (rm -rf on dangerous targets)
    # -----------------------------------------------------------------------
    # The fast-path allowlist runs FIRST so that common safe targets like
    # "node_modules", "./build", "/tmp/..." are never passed to the heavier
    # block-pattern.  This avoids false positives on legitimate cleanup commands
    # and is the critical gate that keeps "git rm -rf src" allowed: "git rm"
    # does not start with "rm " so _RM_SAFE_OPERANDS never even triggers, and
    # _RM_RF_BLOCK will not match it either because "git rm" is not "rm".
    if _RM_RF_BLOCK.search(norm) and not _RM_SAFE_OPERANDS.search(norm):
        _block(
            "Blocked: rm -rf on a protected or dangerous target. "
            "This is a best-effort guard — targets root, home, system dirs, "
            "or bare relative/wildcard operands. "
            "Real boundary: write-scope + guard_write.py + human review."
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

    sys.exit(0)  # fail-open by design (see module docstring)


if __name__ == "__main__":
    main()
