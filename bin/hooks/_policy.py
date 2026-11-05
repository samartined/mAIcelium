"""Shared write policy for the mAIcelium PreToolUse hooks.

Standard library only. The module knows nothing about mAIcelium beyond the
workspace root it is handed, so other tools can reuse it with their own roots.

Single pipeline, no special branches::

    decide(tool_name, tool_input, payload, ws_root) -> Decision(kind, reason)

1. Take the target path from ``tool_input`` (``file_path``, or
   ``notebook_path`` for NotebookEdit). Missing or relative -> deny.
2. Build two identities: ``lexical`` (``abspath``) and ``real`` (``realpath``,
   which also resolves the existing ancestors of a not-yet-created file).
3. ``real`` must fall under one of the write roots, otherwise deny.
4. Every name rule is evaluated on BOTH identities, component by component and
   case-insensitively, so a symlink with an innocent name cannot alias a
   protected file and ``.CLAUDE/settings.json`` is the same as
   ``.claude/settings.json``.
5. The most restrictive decision wins: deny > ask > allow.

Callers turn the decision into hook output with ``emit``. ``allow`` prints
nothing on purpose: an explicit ``permissionDecision: "allow"`` would skip
Claude Code's normal permission prompts, which is not this guard's call.
"""
import collections
import fnmatch
import json
import os
from datetime import datetime, timezone

ALLOW = "allow"
ASK = "ask"
DENY = "deny"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}

Decision = collections.namedtuple("Decision", "kind reason")
ALLOWED = Decision(ALLOW, "")

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pipfile.lock",
    }
)

# `.env.*` names that are templates, not secrets.
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template")

# Layer-managed reflections inside the workspace: these must resolve into a
# layer under mesh/layers/; a real file here is a stale copy.
_REFLECTION_PREFIXES = (
    ("mesh", "skills", "_common"),
    ("mesh", "skills", "_domains"),
    ("mesh", "skills", "_clients"),
    ("mesh", "rules", "_domains"),
    ("mesh", "rules", "_clients"),
)

# Workspace-only, auto-generated paths (relative to the workspace root).
_WS_GENERATED_FILES = (
    ("workspace.md",),
    ("maicelium.code-workspace",),
    (".claude", "projects-context.md"),
)
_WS_GENERATED_DIRS = (
    (".claude", "skills"),
    (".cursor",),
    (".agents",),
    (".antigravity",),
)


# ---------------------------------------------------------------------------
# Decisions and hook output
# ---------------------------------------------------------------------------


def deny(reason):
    return Decision(DENY, reason)


def ask(reason):
    return Decision(ASK, reason)


def strictest(decisions):
    """Return the most restrictive decision (first one wins on a tie)."""
    best = ALLOWED
    for d in decisions:
        if _RANK[d.kind] > _RANK[best.kind]:
            best = d
    return best


def render(decision):
    """Return the hook stdout for *decision* ('' for allow)."""
    if decision.kind == ALLOW:
        return ""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision.kind,
                "permissionDecisionReason": decision.reason,
            }
        }
    )


def emit(decision):
    out = render(decision)
    if out:
        print(out)


def workspace_root(hook_file):
    """Workspace root: MAICELIUM_ROOT (tests) or three levels above the hook."""
    env_root = os.environ.get("MAICELIUM_ROOT")
    if env_root:
        return env_root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(hook_file))))


def log_failure(ws_root, hook, reason):
    """Append one line to <ws>/.claude/hook-failures.log; never raises."""
    try:
        log_path = os.path.join(ws_root, ".claude", "hook-failures.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{ts} {hook} {reason}\n")
    except Exception:  # noqa: BLE001 - logging must never mask a decision
        pass


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def is_under(path, root):
    """True if *path* is *root* or inside it. Never raises on Windows drives:
    paths on another drive simply are not under the root."""
    p, r = _key(path), _key(root)
    if p == r:
        return True
    if not r.endswith(os.sep):
        r += os.sep
    return p.startswith(r)


def _parts(path):
    """Lower-cased components of *path* (drive/anchor dropped)."""
    _, tail = os.path.splitdrive(_key(path))
    return [c.lower() for c in tail.replace("\\", "/").split("/") if c]


def _rel_parts(path, root):
    """Lower-cased components of *path* relative to *root* (caller checks
    ``is_under`` first)."""
    rel = os.path.relpath(_key(path), _key(root))
    if rel == os.curdir:
        return []
    return [c.lower() for c in rel.replace("\\", "/").split("/") if c]


def target_path(tool_name, tool_input):
    if tool_name == "NotebookEdit":
        return tool_input.get("notebook_path")
    path = tool_input.get("file_path")
    if path is None:
        path = tool_input.get("notebook_path")
    return path


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------


def _dedupe(paths):
    seen, out = set(), []
    for p in paths:
        k = _key(p)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def compute_roots(ws_root, payload):
    """Real paths under which writes are allowed.

    - the workspace itself;
    - Claude Code's plan directory ``~/.claude/plans``.
    """
    roots = [
        os.path.realpath(ws_root),
        os.path.realpath(os.path.expanduser(os.path.join("~", ".claude", "plans"))),
    ]
    return _dedupe(roots)


def _layer_roots(ws_root):
    """Real paths that a layer reflection may legitimately resolve into."""
    layers = os.path.join(ws_root, "mesh", "layers")
    roots = [os.path.realpath(layers)]
    try:
        names = os.listdir(layers)
    except OSError:
        names = []
    for name in names:
        roots.append(os.path.realpath(os.path.join(layers, name)))
    return _dedupe(roots)


# ---------------------------------------------------------------------------
# Name rules
# ---------------------------------------------------------------------------


def _generic_rules(path):
    """Rules that apply at any depth, inside any root."""
    parts = _parts(path)
    if not parts:
        return []
    out = []
    base = parts[-1]
    if ".git" in parts:
        out.append(
            deny(
                "Protected path: .git internals (or a .git pointer file) must "
                "not be modified by agents. For a commit message, write it to "
                "the scratchpad and run `git commit -F <path>`."
            )
        )
    if (base == ".env" or base.startswith(".env.")) and not base.endswith(
        ENV_TEMPLATE_SUFFIXES
    ):
        out.append(
            deny(
                f"Protected file: {base}. Environment files may contain secrets "
                f"(templates ending in .example/.sample/.template are allowed)."
            )
        )
    if base in LOCKFILES:
        out.append(
            deny(f"Protected file: {base} is a lockfile. Use the package manager to update it.")
        )
    return out


def _workspace_rules(rel):
    """Rules for paths inside the workspace (``rel`` is lower-cased parts)."""
    if not rel:
        return []
    shown = "/".join(rel)
    out = []
    if tuple(rel) in _WS_GENERATED_FILES:
        out.append(
            deny(
                f"Protected file: {shown} is auto-generated. Use the bin/ scripts "
                f"(`mai sync`) to regenerate it."
            )
        )
    for prefix in _WS_GENERATED_DIRS:
        if tuple(rel[: len(prefix)]) == prefix and len(rel) > len(prefix):
            out.append(
                deny(
                    f"Protected path: {shown} is auto-generated via symlinks by "
                    f"sync_symlinks.py. Write to mesh/ (or the owning layer) instead."
                )
            )
    if len(rel) == 2 and rel[0] == ".claude" and fnmatch.fnmatchcase(rel[1], "settings*.json"):
        out.append(
            ask(
                f"Sensitive file: {shown} holds the agent's own permissions and "
                f"hooks. Confirm only if you asked for this change."
            )
        )
    return out


def _stale_reflection(lexical, real, ws_root):
    ws_lex = os.path.abspath(ws_root)
    if not is_under(lexical, ws_lex):
        return []
    rel = _rel_parts(lexical, ws_lex)
    if not any(tuple(rel[: len(p)]) == p and len(rel) > len(p) for p in _REFLECTION_PREFIXES):
        return []
    if any(is_under(real, r) for r in _layer_roots(ws_root)):
        return []
    return [
        deny(
            f"Layer-managed path: {'/'.join(rel)} is a stale reflection, not a "
            f"symlink to a source-of-truth layer. Edit the canonical file under "
            f"mesh/layers/<layer>/ and run `mai sync`. Current realpath: {real}"
        )
    ]


def check_names(lexical, real, ws_root):
    """Evaluate every name rule on both identities."""
    ws_roots = _dedupe([os.path.abspath(ws_root), os.path.realpath(ws_root)])
    out = []
    for ident in _dedupe([lexical, real]):
        out.extend(_generic_rules(ident))
        for wr in ws_roots:
            if is_under(ident, wr):
                out.extend(_workspace_rules(_rel_parts(ident, wr)))
    out.extend(_stale_reflection(lexical, real, ws_root))
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def decide(tool_name, tool_input, payload, ws_root):
    if not isinstance(tool_input, dict):
        return deny("Blocked: hook input has no tool_input object.")
    path = target_path(tool_name, tool_input)
    if not isinstance(path, str) or not path:
        return deny("Blocked: hook input has no file path to check.")
    if not os.path.isabs(path):
        return deny(f"Blocked: file path '{path}' is not absolute.")

    lexical = os.path.abspath(path)
    real = os.path.realpath(path)

    roots = compute_roots(ws_root, payload if isinstance(payload, dict) else {})
    if not any(is_under(real, r) for r in roots):
        return deny(
            f"Blocked: file_path '{path}' is outside the workspace "
            f"(resolves to '{real}'). Refusing write as a safety measure."
        )

    return strictest(check_names(lexical, real, ws_root))
