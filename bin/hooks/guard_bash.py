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

COVERED (common literal destructive cases — best-effort, NOT guaranteed
false-positive-free or complete)
---------------------------------------------------------------------
This list is what the regexes *aim* to catch.  It is a best-effort speed-bump,
not a complete or provably false-positive-free matcher: novel quoting,
wrapper, or encoding tricks can still slip past or, in principle, mis-fire.
  * rm -rf / rm -fr on protected root paths: /, /etc, /home, /usr, /var,
    /bin, /lib, /lib64, /boot, /root, /sys, /proc, /dev, /opt, /srv,
    /sbin (and subpaths thereof, e.g. /home/user, /etc/*)
  * rm -rf on the bare root followed by a glob/dotfile: /* /.* /*.txt /.bashrc
  * A RUN of leading slashes is treated like a single leading slash, because
    the kernel collapses them (``//`` and ``///`` resolve to ``/``).  So
    ``//``, ``///``, ``//*``, ``//etc``, ``//home/user``, ``//.bashrc`` block
    exactly like their single-slash forms.
  * rm -rf on bare cwd/parent/wildcard operands: . .. ./ ../ * ./*
  * rm -rf on ~ / ~/... / $HOME / ${HOME}
  * Per-segment evaluation of compound commands: a dangerous rm -rf in ANY
    segment (split on && || ; | and newlines) blocks the whole command even
    when other segments are safe (e.g. ``rm -rf dist && rm -rf /`` is blocked);
    the safe-operand allowlist only ever waives the block within its own
    segment.
  * Command-position anchoring: ``rm -rf`` is treated as dangerous only when
    ``rm`` is the command actually being run in a segment — after stripping a
    leading run of common wrappers (``sudo`` / ``doas`` INCLUDING their
    flag-only options, ``time``, ``nice [-n N]``, ``env VAR=val ...``).  So
    ``sudo rm -rf /`` AND flagged forms like ``sudo -i rm -rf /``,
    ``sudo --preserve-env rm -rf /`` and ``doas -n rm -rf /`` block, while a
    segment whose command is something else (git/grep/echo/cat/...) is NOT
    blocked merely because it CONTAINS the literal string ``rm -rf /...`` in a
    quoted argument (e.g. ``git commit -m "...rm -rf /..."`` and
    ``grep "rm -rf /" .`` are allowed).
  * Full path to rm: an OPTIONAL path prefix that ENDS IN ``/`` is allowed at
    the anchored command position, so ``/bin/rm -rf /`` and ``/usr/bin/rm -rf
    /etc`` block.  The required trailing ``/`` means only a genuine path matches
    — a word that merely ends in ``rm`` (``charm``, ``myrm``) or a flag
    (``--rm``) never does, so ``git rm -rf src`` and ``charm -rf foo`` stay
    allowed.  The safe-operand allowlist accepts the same prefix, so
    ``/bin/rm -rf node_modules`` stays allowed too.
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
  * sudo -u root rm -rf /      (sudo/doas flag that takes a SEPARATE value
                                argument: only flag-only options are consumed;
                                consuming a value generically would wrongly
                                swallow ``rm`` in value-less forms like
                                ``sudo -i rm`` and under-block, so the value
                                form is left as a gap rather than risk it)
  * stdbuf rm -rf / ; setsid rm -rf / ; timeout 5 rm -rf / ; command rm -rf / ;
    \\rm -rf /                  (wrappers / quoting tricks beyond the small
                                stripped set sudo|doas|time|nice|env)
  * rm --recursive --force /   (GNU long-form flags: the flag matcher targets
                                the common short clusters ``-rf``/``-fr``)
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

# Alternation of NON-bare protected root NAMES (everything except "/", with the
# leading slash stripped: "etc", "home", ...).  The leading slash is factored
# out of the alternation so a single ``/+`` in _RM_RF_BLOCK can consume a RUN of
# leading slashes ahead of the name (the kernel collapses ``//etc`` to ``/etc``,
# so it must block identically — Finding 1).  The bare root "/" itself is handled
# by dedicated branches in _RM_RF_BLOCK because, unlike a named root such as
# "/etc", a bare "/" must NOT greedily swallow an ordinary subpath like
# "/tmp/foo" (that would be a false positive) — it may only match when it is the
# whole operand ("rm -rf /", "rm -rf //") or is immediately followed by a
# glob/dotfile metachar ("rm -rf /*", "rm -rf //.bashrc").
_PROT_NONROOT_NAMES = "|".join(
    re.escape(r[1:])  # drop the leading "/" — restored as "/+" in the regex
    for r in sorted((x for x in _PROTECTED_ROOTS if x != "/"), key=len, reverse=True)
)

# The complete rm -rf guard (assembled at module load; not inside a loop to
# avoid ReDoS — all alternations are linear prefix-anchored strings).
#
# An operand is captured after optional quoting and optional "--" separator.
# The lookahead (?=[\s"'$]|$) ensures we match only at the END of the operand
# token, which prevents matching subpaths of non-protected directories
# (e.g. "rm -rf ./build" must NOT match even though it starts with ".").
#
# Operand classes:
#  A) protected absolute root (exact, or with subpath, or bare-root + glob)
#  B) bare relative dangerous operands: . .. ./ ../ * ./*
#  C) home shortcuts: ~ ~/ $home ${home}
#
# Bare-root coverage (Finding 1): the catastrophic ``rm -rf /*`` family is a
# bare root "/" immediately followed by a glob/dotfile (``*``, ``.bashrc``,
# ``.*``, ``*.txt``).  A named root such as ``/etc`` can safely use the
# ``(?:/subpath)?`` tail, but the bare root "/" cannot (it would then match an
# ordinary ``/tmp/foo`` and create a false positive).  So the bare root gets
# two dedicated branches: (A2) "/" + glob/dotfile metachar + rest, and (A3) a
# lone "/" that is the entire operand.
#
# Leading-slash RUN (Finding 1, round 3): every absolute branch consumes a RUN
# of leading slashes ``/+`` instead of a single ``/``.  The kernel collapses
# consecutive leading slashes (``//`` and ``///`` resolve to ``/``;
# ``bash -c 'echo //*'`` globs the root filesystem identically to ``/*``), so
# ``//``, ``///``, ``//*``, ``//etc``, ``//home/user`` and ``//.bashrc`` MUST
# block exactly like their single-slash forms.  ``/+`` only matches LEADING
# slashes of the operand; embedded ``//`` in a relative path (``foo//bar``) is
# untouched because the operand does not start with ``/``.
#
# Command-position anchoring (Finding 2): the pattern is anchored with ``^`` and
# applied in _command_is_dangerous only AFTER leading wrappers are stripped from
# the segment, so it fires only when ``rm`` is the command actually being run —
# not when ``rm -rf /...`` merely appears inside a quoted argument to another
# command (``git commit -m "...rm -rf /..."``, ``grep "rm -rf /" .``).
_RM_RF_BLOCK = re.compile(
    r"""
    ^                             # command position (segment start, post-wrapper)
    (?:\S*/)?                     # optional path prefix that ENDS IN "/" (e.g.
                                  # /bin/, /usr/bin/) so a full path to rm is
                                  # covered; the trailing "/" means only a real
                                  # path matches, never a word ending in "rm"
                                  # (charm) or a flag (--rm)
    rm \s+                        # rm command
    (?:                           # optional flags block (e.g. -rf -- or -fr)
      -[a-z]*[rf][a-z]* \s+
    ){1,4}
    (?:--\s+)?                    # optional -- separator
    (?P<q>['"])?                  # optional opening quote
    (?:                           # operand alternatives
      # A1) named protected root (/etc, /home, ...): exact or /subpath or /glob,
      #     preceded by a RUN of leading slashes (//etc collapses to /etc)
      /+ (?:""" + _PROT_NONROOT_NAMES + r""")(?:/[^\s"']*)?
      |
      # A2) bare root run "/+" + glob/dotfile metachar + remainder (rm -rf /*,
      #     //*, /.*, /.bashrc, /*.txt) — the lookahead keeps /tmp/foo out here
      /+(?=[*?.\[~])[^\s"']*
      |
      # A3) bare root run "/+" as the entire operand (rm -rf /, //, ///)
      /+
      |
      # B) bare relative dangerous operands (whole operand only)
      \.\.?/?
      |
      # C) wildcards
      \./?\*?(?!\w)
      |
      \*
      |
      # D) home shortcuts ($home and brace form ${home})
      ~(?:/[^\s"']*)?
      |
      \$\{?home\}?(?:/[^\s"']*)?
    )
    (?P=q)?                       # matching closing quote (back-reference)
    (?=\s|"|'|$)                  # end of operand token
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Safe-operand allowlist — if the rm -rf operand matches one of these the
# block is waived.  Checked PER SEGMENT (see _command_is_dangerous) against the
# same wrapper-stripped, command-position-anchored segment as _RM_RF_BLOCK, so
# the allowlist may only ever waive the block for an rm -rf within its OWN
# segment, never for a dangerous rm -rf elsewhere in a compound command
# (Finding 2).  Anchored with ``^`` for the same command-position reason, and it
# accepts the same optional ``(?:\S*/)?`` path prefix as _RM_RF_BLOCK so a safe
# operand stays allowed even when rm is invoked by full path (``/bin/rm -rf
# node_modules`` must NOT block).
_RM_SAFE_OPERANDS = re.compile(
    r"^(?:\S*/)?rm\s+-[a-z]*[rf][a-z]*\s+(?:--\s+)?"
    r"(?:"
    r"node_modules"
    r"|__pycache__"
    r"|\.cache"
    r"|(?:\./)?(dist|build|target|out|coverage)"
    r"|/tmp/"
    r")",
    re.IGNORECASE,
)

# Command separators used to split a compound command into independently
# evaluated segments: && || ; | and newlines.  Splitting on these prevents a
# safe ``rm -rf <allowlisted>`` in one segment from waiving the block on a
# dangerous ``rm -rf /`` in another (Finding 2).  This is a deliberately
# shallow split (it does not understand quotes/subshells) which is consistent
# with the best-effort, fail-open nature of the hook: at worst it over-splits,
# which can only make the guard MORE conservative, never less.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")

# Leading command WRAPPERS that delegate to a real command (Finding 2).  A
# segment beginning with a run of these still counts as an ``rm`` invocation if
# ``rm`` is what they ultimately run, so they are stripped before the
# command-position-anchored _RM_RF_BLOCK / _RM_SAFE_OPERANDS check.  Covered:
#   sudo / doas            privilege escalation, INCLUDING flag-only options
#                          (``sudo -i``, ``sudo --preserve-env``, ``doas -n``)
#   time                   timing wrapper
#   nice [-n N]            scheduling-priority wrapper
#   env VAR=val ...        environment-setting wrapper (zero or more assignments)
# The sudo/doas ``(?:\s+-{1,2}\S+)*`` tail consumes only FLAG tokens (those
# starting with ``-``); it deliberately does NOT consume a flag's separate value
# argument, so ``sudo -u <user> rm`` (where ``<user>`` is the arg to ``-u``) is a
# DOCUMENTED residual gap.  Consuming the value generically is unsafe: it would
# swallow ``rm`` itself in ``sudo -i rm`` (a value-less flag) and UNDER-block, so
# the value form is intentionally left as a best-effort gap rather than risk
# either a regression or over-blocking ``sudo <prog> <arg> ...``.
# This is a deliberately SMALL, best-effort set.  Wrappers OUTSIDE it (e.g.
# ``stdbuf``, ``xargs``, ``timeout``, ``setsid``, ``command``, arbitrary
# ``env <prog>``) are a residual gap, consistent with the documented
# variable-indirection / command-substitution gaps — anchoring is NOT claimed to
# be complete.  The anchored ``\d+`` for ``nice -n``, ``\S+=\S+`` for ``env`` and
# the single-star ``(?:\s+-{1,2}\S+)*`` for sudo/doas keep this linear.
_LEADING_WRAPPERS = re.compile(
    r"^\s*(?:(?:"
    r"sudo(?:\s+-{1,2}\S+)*"      # sudo + flag-only options (-i, --preserve-env)
    r"|doas(?:\s+-{1,2}\S+)*"     # doas + flag-only options (-n)
    r"|time"
    r"|nice(?:\s+-n\s+\d+)?"
    r"|env(?:\s+\S+=\S+)*"
    r")\s+)+",
    re.IGNORECASE,
)


def _command_is_dangerous(cmd):
    """Return True if any segment of *cmd* is a blockable rm -rf invocation.

    The raw (lower-cased) command is split into segments on command separators
    and EACH segment is evaluated independently.  Within a segment, leading
    command wrappers (``sudo`` / ``doas`` with their flag-only options,
    ``time``, ``nice [-n N]``, ``env VAR=val ...``) are stripped, then the
    command-position-anchored ``_RM_RF_BLOCK`` must match AND
    ``_RM_SAFE_OPERANDS`` must not.  Because the block pattern is anchored at the
    (post-wrapper) segment start — allowing only an optional ``/``-terminated
    path prefix before ``rm`` — ``rm -rf`` is treated as dangerous only when
    ``rm`` (possibly via a full path like ``/bin/rm``) is the command actually
    being run.

    A single dangerous segment blocks the whole command regardless of how many
    safe segments accompany it; conversely the safe-operand allowlist can only
    waive the block within the segment it appears in.

    Consequences (all intentional):
      * ``git rm -rf src`` / ``cd app && rm -rf dist`` stay allowed.
      * ``git commit -m "...rm -rf /..."``, ``grep "rm -rf /" .`` and other
        commands that merely CONTAIN the literal string ``rm -rf /...`` in a
        quoted argument are allowed (the segment's command is git/grep/...,
        not rm) — Finding 2.
      * ``sudo rm -rf /`` / ``doas rm -rf /`` still block (wrappers stripped),
        as do their flagged forms ``sudo -i rm -rf /`` /
        ``sudo --preserve-env rm -rf /`` / ``doas -n rm -rf /``.
      * ``/bin/rm -rf /`` / ``/usr/bin/rm -rf /etc`` block (full path to rm);
        ``/bin/rm -rf node_modules`` stays allowed (safe operand).
      * Wrappers beyond the listed set, a sudo/doas flag taking a SEPARATE value
        argument (``sudo -u root rm``), and GNU long flags are residual
        best-effort gaps (see module docstring).
    """
    lowered = cmd.lower()
    for segment in _SEGMENT_SPLIT.split(lowered):
        # Normalise each segment the same way the whole command used to be
        # (collapse whitespace, append a trailing space so operand-terminating
        # lookaheads still fire at end of segment).
        seg_norm = " ".join(segment.split()) + " "
        # Strip leading wrappers so the command-position anchor sees the real
        # command token; only then is this segment an ``rm`` invocation.
        seg_cmd = _LEADING_WRAPPERS.sub("", seg_norm, count=1)
        if _RM_RF_BLOCK.search(seg_cmd) and not _RM_SAFE_OPERANDS.search(seg_cmd):
            return True
    return False


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


def _evaluate(cmd):
    """Run every block check against *cmd*.

    Calls ``_block`` (which exits 0 with a block decision) on the first match,
    otherwise returns normally.  Isolated from stdin handling so the caller can
    wrap it in a fail-open guard (see ``main``).
    """
    # Normalise: collapse whitespace, lowercase for pattern matching.
    # Append a trailing space so patterns anchored on a following whitespace
    # (e.g. "/ " or "~ ") still match when the command ends at the target.
    norm = " ".join(cmd.lower().split()) + " "

    # -----------------------------------------------------------------------
    # Catastrophic deletion guard (rm -rf on dangerous targets)
    # -----------------------------------------------------------------------
    # Evaluated PER SEGMENT (Finding 2): the command is split on separators and
    # each segment is wrapper-stripped then checked at command position
    # (block-pattern matches AND safe-operand allowlist does not).  A safe
    # ``rm -rf dist`` can no longer waive the block on a dangerous ``rm -rf /``
    # in another segment.  ``git rm -rf src`` stays allowed because its segment's
    # command is ``git`` (the anchored block-pattern needs ``rm`` at command
    # position), ``cd app && rm -rf dist`` stays allowed because the only rm
    # segment hits the allowlist, and ``grep "rm -rf /" .`` stays allowed
    # because its command is ``grep`` (the literal string is just an argument).
    # See _command_is_dangerous for the full rationale.
    if _command_is_dangerous(cmd):
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

    # Fail-open guard (Finding 3): any UNEXPECTED error in the matching logic
    # must exit 0 without blocking, matching the documented contract.  A
    # legitimate block raises SystemExit (from _block); SystemExit derives from
    # BaseException, not Exception, so it propagates through untouched and the
    # block decision is preserved.
    try:
        _evaluate(cmd)
    except Exception as e:  # noqa: BLE001 — intentional broad fail-open
        _log_failure(f"evaluate-error: {type(e).__name__}: {e}")
        sys.exit(0)  # fail-open by design (see module docstring)

    sys.exit(0)  # fail-open by design (see module docstring)


if __name__ == "__main__":
    main()
