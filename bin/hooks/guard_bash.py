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

The hook FAILS CLOSED (logged to .claude/hook-failures.log):
  - If stdin is malformed, the hook denies the command.
  - If an unexpected exception occurs, the hook denies the command.
  Being a speed-bump is about what it can *detect*; when it cannot run its
  checks at all it refuses rather than waving everything through.
  Real security boundaries are:
    1. Workspace write-scope enforcement via guard_write.py
    2. Human review of agent-proposed commands
    3. Principle of least privilege on the OS side

Decisions are printed as ``hookSpecificOutput.permissionDecision`` (deny or
ask); an allowed command prints nothing.

THREE LAYERS (see docs/security-model.md)
-----------------------------------------
  1. Patterns on commands, not data: heredoc bodies are dropped and quoted
     phrases are blanked before the pattern rules below run.
  2. Destinations through the write policy: every redirection and tee target
     goes through ``_policy.decide`` (the same pipeline as guard_write).
     Agent content (heredoc, herestring, echo, printf) gets Write's decision;
     program output to a protected name is an ask; outside the write roots is
     a deny.
  3. Mounts and guard files: ``ln`` into <ws>/projects/ or <ws>/mesh/ and
     write verbs on bin/hooks/*.py, bin/py.sh, bin/py.cmd or the workspace's
     .claude/settings*.json are denied.

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
import shlex
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
# with the best-effort nature of the hook: at worst it over-splits,
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


# ---------------------------------------------------------------------------
# Command vs. data: heredoc bodies and quoted literals
# ---------------------------------------------------------------------------
# A heredoc body or a quoted phrase is data the command receives, not a command
# the shell runs. Matching patterns against it made a Terraform plan or a script
# that merely MENTIONS ``chmod 777`` or a destructive SQL statement look
# dangerous, and since heredocs were the usual way around guard_write the two
# guards multiplied.

_QUOTED = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*\"""")

# A heredoc operator: << or <<- followed by an optionally quoted delimiter.
# The lookarounds keep the herestring operator <<< out.
_HEREDOC_OP = re.compile(
    r"""(?<!<)<<(?!<)(-?)\s*(?:'([^']*)'|"([^"]*)"|\\?([A-Za-z_][\w.-]*))"""
)


def _blank_quotes(line):
    """Replace quoted strings with same-length filler so operators inside
    quotes are not mistaken for real ones (positions are preserved)."""
    return _QUOTED.sub(lambda m: "_" * len(m.group(0)), line)


def split_heredocs(cmd):
    """Return (code, heredoc_count): *cmd* without heredoc bodies.

    The line holding the ``<<DELIM`` operator stays, so callers still see that
    the command reads a heredoc; the body lines up to the closing delimiter are
    dropped. Operators inside quotes are ignored, so ``echo "<<X"`` does not
    swallow the following lines. An unterminated body runs to the end, as in
    the shell.
    """
    out, pending, count = [], [], 0
    for line in cmd.split("\n"):
        if pending:
            strip_tabs, delim = pending[0]
            candidate = line.lstrip("\t") if strip_tabs else line
            if candidate == delim:
                pending.pop(0)
            continue
        out.append(line)
        for m in _HEREDOC_OP.finditer(_blank_quotes(line)):
            # Re-read the operator from the original line: blanking only
            # touched quoted text, so a quoted delimiter ('EOF') is restored.
            g = _HEREDOC_OP.match(line, m.start()) or m
            if g.group(2) is not None:
                delim = g.group(2)
            elif g.group(3) is not None:
                delim = g.group(3)
            else:
                delim = g.group(4)
            pending.append((g.group(1) == "-", delim))
            count += 1
    return "\n".join(out), count


def _unquote_words(code):
    """Quoted single words become bare words (``"main"`` -> ``main``); quoted
    phrases (anything with whitespace) are blanked: they are messages, prompts
    or source code passed as an argument, not commands."""

    def repl(m):
        inner = m.group(0)[1:-1]
        return inner if inner and not any(c.isspace() for c in inner) else '""'

    return _QUOTED.sub(repl, code)


# ---------------------------------------------------------------------------
# Where does the command write? Redirections and tee, judged by _policy
# ---------------------------------------------------------------------------
# The rule of gold: judge the destination file, not the tool that writes it. A
# redirection target or a tee argument goes through the same _policy.decide as a
# Write. What changes is who produced the bytes:
#   * agent content -- a heredoc (<<, <<-), a herestring (<<<), echo or printf:
#     the same decision as Write (``cat <<EOF > .env`` is a deny);
#   * program output -- anything else (``./tool.py > .env``,
#     ``sops -d x | tee .env``): an ask on a protected name, because the secret
#     never passed through the agent but the destination is sensitive.
# A target outside every write root is a deny either way. What a script does
# inside (open(".env", "w") in Python) is invisible here, by design.

_OPERATORS = (
    "&>>", "&&", "||", "|&", ">>", ">|", ">&", "<<<", "<<", "<&", "&>",
    ">", "<", "|", ";", "&", "(", ")",
)
_SEPARATORS = frozenset({"&&", "||", ";", "&", "(", ")"})
_PIPES = frozenset({"|", "|&"})
_REDIRECT_OUT = frozenset({">", ">>", ">|", "&>", "&>>"})
_AGENT_PRODUCERS = frozenset({"echo", "printf"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_UNRESOLVABLE = set("$`*?[{")


def _split_punct(tok):
    """shlex groups adjacent punctuation (``)>``); split it into operators."""
    out, i = [], 0
    while i < len(tok):
        for op in _OPERATORS:
            if tok.startswith(op, i):
                out.append(op)
                i += len(op)
                break
        else:
            out.append(tok[i])
            i += 1
    return out


def _tokens(line):
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    out = []
    for tok in lex:
        if tok and all(c in "();<>|&" for c in tok):
            out.extend(_split_punct(tok))
        else:
            out.append(tok)
    return out


def _pipelines(code):
    """Yield each pipeline as a list of stages (lists of tokens). Lines that
    shlex cannot parse (unbalanced quotes) are skipped: this layer is a
    speed-bump, and the pattern rules above still saw them."""
    for line in code.split("\n"):
        try:
            toks = _tokens(line)
        except ValueError:
            continue
        pipeline, stage = [], []
        for t in toks:
            if t in _SEPARATORS:
                if stage:
                    pipeline.append(stage)
                if pipeline:
                    yield pipeline
                pipeline, stage = [], []
            elif t in _PIPES:
                pipeline.append(stage)
                stage = []
            else:
                stage.append(t)
        if stage:
            pipeline.append(stage)
        if pipeline:
            yield pipeline


def _strip_wrappers(words):
    """Drop leading assignments and the wrappers guard_bash already knows
    (sudo/doas with flag options, time, nice [-n N], env [VAR=val ...])."""
    i = 0
    while i < len(words):
        w = words[i]
        base = os.path.basename(w)
        if _ASSIGNMENT.match(w):
            i += 1
        elif base in ("sudo", "doas", "env"):
            i += 1
            while i < len(words) and (words[i].startswith("-") or _ASSIGNMENT.match(words[i])):
                i += 1
        elif base == "time":
            i += 1
        elif base == "nice":
            i += 1
            if i + 1 < len(words) and words[i] == "-n":
                i += 2
        else:
            break
    return words[i:]


class _Stage:
    __slots__ = ("cmd", "args", "targets", "agent")

    def __init__(self, tokens):
        words, targets, agent = [], [], False
        i = 0
        while i < len(tokens):
            t = tokens[i]
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if t in _REDIRECT_OUT:
                if words and words[-1] in ("1", "2"):
                    words.pop()  # the fd number of 2> / 1>>
                if nxt is not None:
                    targets.append(nxt)
                i += 2
                continue
            if t == ">&":
                if words and words[-1] in ("1", "2"):
                    words.pop()
                if nxt is not None and not (nxt.isdigit() or nxt == "-"):
                    targets.append(nxt)  # csh-style ">& file"
                i += 2
                continue
            if t in ("<<", "<<<"):
                agent = True
                i += 2
                continue
            if t in ("<", "<&"):
                i += 2
                continue
            words.append(t)
            i += 1
        words = _strip_wrappers(words)
        self.cmd = os.path.basename(words[0]) if words else ""
        self.args = words[1:]
        self.targets = targets
        self.agent = agent or self.cmd in _AGENT_PRODUCERS


def _stages(code):
    for pipeline in _pipelines(code):
        yield [_Stage(st) for st in pipeline]


def _resolve(tok, cwd):
    """Absolute path for a shell word, or None when it cannot be known
    statically (variables other than $HOME, globs, command substitution)."""
    if not tok or tok == "-" or tok.startswith("/dev/"):
        return None
    home = os.path.expanduser("~")
    if tok == "~" or tok.startswith("~/"):
        tok = home + tok[1:]
    for var in ("${HOME}", "$HOME"):
        if tok == var or tok.startswith(var + "/"):
            tok = home + tok[len(var):]
            break
    if any(c in _UNRESOLVABLE for c in tok):
        return None
    if not os.path.isabs(tok):
        tok = os.path.join(cwd, tok)
    return os.path.abspath(tok)


def _payload_cwd(payload):
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd and "\x00" not in cwd and os.path.isabs(cwd):
        return cwd
    return os.getcwd()


def _write_targets(code, cwd):
    """Yield (token, path, agent_content) for every redirection and tee target."""
    for stages in _stages(code):
        previous_agent = False
        for st in stages:
            for tok in st.targets:
                yield tok, _resolve(tok, cwd), st.agent
            if st.cmd == "tee":
                for tok in st.args:
                    if not tok.startswith("-"):
                        yield tok, _resolve(tok, cwd), previous_agent
            previous_agent = st.agent


def _target_decision(policy, tok, path, agent, payload, ws_root):
    d = policy.decide("Write", {"file_path": path}, payload, ws_root)
    if d.kind == policy.ALLOW:
        return d
    if d.scope == policy.PERIMETER:
        return policy.deny(f"Blocked: shell output to '{tok}'. {d.reason}", policy.PERIMETER)
    if agent:
        return d  # same decision and message as a Write of that content
    return policy.ask(
        f"Program output redirected to a protected file ('{tok}'). {d.reason} "
        f"The content does not pass through the agent, so this is a confirmation, "
        f"not a block."
    )


# Write verbs that must not touch the guard files (#44, Bash side). Reading them
# (cat, grep, rg, git diff, pytest) stays allowed.
_GUARD_WRITE_CMDS = frozenset({"cp", "mv", "rm", "chmod", "truncate", "install", "patch", "tee"})


def _writes_operands(st):
    """True if this stage's command writes to (some of) its operands."""
    if st.cmd in _GUARD_WRITE_CMDS:
        return True
    if st.cmd == "sed":
        return any(
            a.startswith("--in-place")
            or (a.startswith("-") and not a.startswith("--") and "i" in a[1:])
            for a in st.args
        )
    if st.cmd == "git" and st.args:
        sub = st.args[0]
        return (sub == "checkout" and "--" in st.args) or sub == "restore"
    return False


def _guard_message(tok):
    return (
        f"Blocked: this command would modify the guard file '{tok}'. The guards "
        f"and the workspace settings can only change through Write/Edit, where "
        f"the user confirms each change. Ask the user if this change is intended."
    )


def _ln_destination(st, cwd):
    """Where an ``ln`` invocation creates its link(s), as an absolute path."""
    target_dir, operands, args, i = None, [], st.args, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            operands.extend(args[i + 1:])
            break
        if a == "--target-directory" or (a.startswith("-") and not a.startswith("--") and a.endswith("t")):
            target_dir = args[i + 1] if i + 1 < len(args) else None
            i += 2
            continue
        if a.startswith("--target-directory="):
            target_dir = a.split("=", 1)[1]
        elif a.startswith("-t") and len(a) > 2:
            target_dir = a[2:]
        elif not a.startswith("-"):
            operands.append(a)
        i += 1
    if target_dir:
        return _resolve(target_dir, cwd)
    if len(operands) >= 2:
        return _resolve(operands[-1], cwd)
    if len(operands) == 1:
        return os.path.abspath(cwd)
    return None


def _is_mount_folder_target(path, ws_root, policy):
    """True if *path* is <ws>/projects/... or <ws>/mesh/... (either identity)."""
    bases = []
    for ws in {os.path.abspath(ws_root), os.path.realpath(ws_root)}:
        bases += [os.path.join(ws, "projects"), os.path.join(ws, "mesh")]
    idents = {os.path.abspath(path), os.path.realpath(path)}
    return any(policy.is_under(i, b) for i in idents for b in bases)


def _command_decisions(code, cwd, ws_root, policy):
    """ln into the mount folders, and write verbs on the guard files."""
    out = []
    for stages in _stages(code):
        for st in stages:
            if st.cmd == "ln":
                dest = _ln_destination(st, cwd)
                if dest and _is_mount_folder_target(dest, ws_root, policy):
                    out.append(
                        policy.deny(
                            "Blocked: `ln` into projects/ or mesh/. Those folders hold "
                            "the mounts mAIcelium manages, and a hand-made link there "
                            "becomes a write root. Mount repos with `mai add <name> "
                            "<path>`, layers with `mai add-layer <name> <path>` and MCP "
                            "sources with `mai add-mcp <path>`."
                        )
                    )
            if _writes_operands(st):
                for tok in st.args:
                    if tok.startswith("-"):
                        continue
                    path = _resolve(tok, cwd)
                    if path and policy.is_guard_target(path, ws_root):
                        out.append(policy.deny(_guard_message(tok)))
    return out


def structural_decisions(code, payload, ws_root, policy):
    """Decisions for where *code* (heredoc bodies already removed) writes."""
    cwd = _payload_cwd(payload)
    out = _command_decisions(code, cwd, ws_root, policy)
    for tok, path, agent in _write_targets(code, cwd):
        if path is None:
            continue
        if policy.is_guard_target(path, ws_root):
            out.append(policy.deny(_guard_message(tok)))
        else:
            out.append(_target_decision(policy, tok, path, agent, payload, ws_root))
    return out


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


_HOOK = "guard_bash"


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
            f.write(f"{ts} {_HOOK} {reason}\n")
    except OSError:
        pass


def _deny(reason):
    """Print a deny decision (current hook output contract)."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _block(reason):
    _deny(reason)
    sys.exit(0)


def _evaluate(cmd, payload=None, ws_root=None, policy=None):
    """Run every block check against *cmd*.

    Calls ``_block`` (which exits 0 with a deny decision) on the first match,
    otherwise returns normally.  Isolated from stdin handling so the caller can
    wrap it in a fail-closed guard (see ``main``).
    """
    # Heredoc bodies are data: drop them before any pattern runs.
    cmd, _ = split_heredocs(cmd)
    code = cmd
    # Normalise: collapse whitespace, lowercase for pattern matching.
    # Append a trailing space so patterns anchored on a following whitespace
    # (e.g. "/ " or "~ ") still match when the command ends at the target.
    # ``norm`` keeps quoted text, because SQL is normally passed quoted to a
    # client (psql -c "..."); ``bare`` blanks quoted phrases for the rules that
    # only make sense on real command words (chmod, force push, mkfs/dd).
    norm = " ".join(cmd.lower().split()) + " "
    bare = " ".join(_unquote_words(cmd).lower().split()) + " "

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
    if re.search(r"git\s+push\s+.*(-f|--force)", bare) and re.search(
        r"\b(main|master)\b", bare
    ):
        _block(
            "Blocked: force push to main/master. "
            "This rewrites shared history."
        )

    # Dangerous disk ops
    if re.search(r"(mkfs\.|>\s*/dev/sd|dd\s+if=.*/dev/)", bare):
        _block(
            "Blocked: low-level disk operation (mkfs/dd). "
            "This could destroy disk data."
        )

    # chmod 777
    if re.search(r"chmod\s+777", bare):
        _block(
            "Blocked: chmod 777 sets world-writable permissions. "
            "Use more restrictive permissions."
        )

    if policy is None:
        return None
    return policy.strictest(
        structural_decisions(code, payload or {}, ws_root, policy)
    )


def _read_command():
    """Return the command string, or None after denying malformed input."""
    try:
        data = json.loads(sys.stdin.read())
    except ValueError as e:
        _log_failure(f"stdin-parse-error: {e}")
        _deny(f"{_HOOK}: invalid hook input (not JSON); refusing.")
        return None
    if not isinstance(data, dict):
        _log_failure("stdin-not-object")
        _deny(f"{_HOOK}: invalid hook input (not an object); refusing.")
        return None
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        _deny(f"{_HOOK}: hook input has no tool_input object; refusing.")
        return None
    cmd = tool_input.get("command", "")
    if not isinstance(cmd, str):
        _deny(f"{_HOOK}: command is not a string; refusing.")
        return None
    return cmd, data


def main():
    # Fail closed: a legitimate block raises SystemExit (from _block), which
    # derives from BaseException and passes through untouched; any other
    # exception means the checks could not run, so the command is denied.
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import _policy

        read = _read_command()
        if read and read[0]:
            cmd, data = read
            decision = _evaluate(cmd, data, _get_root(), _policy)
            if decision is not None:
                _policy.emit(decision)
    except Exception as e:  # noqa: BLE001 - intentional broad fail-closed
        reason = f"{_HOOK} crashed: {type(e).__name__}: {e}"
        _log_failure(reason)
        _deny(f"Blocked: {reason}. Refusing as a safety measure.")
    sys.exit(0)


if __name__ == "__main__":
    main()
