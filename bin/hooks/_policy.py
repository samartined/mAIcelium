"""Shared write policy for the mAIcelium PreToolUse hooks.

Standard library only. The module knows nothing about mAIcelium beyond the
workspace root it is handed, so other tools can reuse it with their own roots.

Single pipeline, no special branches::

    decide(tool_name, tool_input, payload, ws_root) -> Decision(kind, reason)

1. Take the target path from ``tool_input`` (``file_path``, or
   ``notebook_path`` for NotebookEdit). Missing or relative -> deny.
2. Build two identities: ``lexical`` (``abspath``) and ``real`` (``realpath``,
   which also resolves the existing ancestors of a not-yet-created file).
3. ``real`` must fall under one of the write roots (``compute_roots``),
   otherwise deny. Mount targets are filtered by ``acceptable_mount`` so a
   symlink such as ``mesh/layers/evil -> ~`` never turns $HOME into a root.
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
import tempfile
from datetime import datetime, timezone

ALLOW = "allow"
ASK = "ask"
DENY = "deny"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}

# ``scope`` says which part of the pipeline decided: "perimeter" (the target is
# outside every write root, or the input is unusable) or "name" (a name rule).
# guard_bash needs it to tell "never write there" from "sensitive file".
Decision = collections.namedtuple("Decision", "kind reason scope", defaults=("name",))
PERIMETER = "perimeter"
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

# Key and credential material: writes need a human confirmation.
KEY_MATERIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kubeconfig")

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


def deny(reason, scope="name"):
    return Decision(DENY, reason, scope)


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


def _home():
    return os.path.realpath(os.path.expanduser("~"))


def acceptable_mount(real, ws_root):
    """False for targets that must never become a write root, whatever a
    symlink under the workspace says: a disk/drive root, $HOME or anything
    containing it, the workspace or anything containing it, and anything under
    a hidden folder of $HOME (which covers ~/.claude, ~/.ssh, ~/.aws, ...)."""
    if os.path.dirname(real) == real:
        return False
    home = _home()
    if is_under(home, real):
        return False
    if is_under(os.path.realpath(ws_root), real):
        return False
    if is_under(real, home):
        rel = _rel_parts(real, home)
        if rel and rel[0].startswith("."):
            return False
    return True


def _mount_children(ws_root, *rel_dirs):
    """Real paths of the direct children of <ws>/<rel_dirs>, filtered.

    Every directory on the way (e.g. ``mesh`` and ``mesh/layers``) must be a
    real directory: if one of them is a symlink, nobody can tell what it
    mounts, so it contributes no roots."""
    current = ws_root
    for name in rel_dirs:
        current = os.path.join(current, name)
        if os.path.islink(current) or not os.path.isdir(current):
            return []
    out = []
    try:
        names = sorted(os.listdir(current))
    except OSError:
        return []
    for name in names:
        real = os.path.realpath(os.path.join(current, name))
        if os.path.isdir(real) and acceptable_mount(real, ws_root):
            out.append(real)
    return out


def layer_roots(ws_root):
    """Real paths of the layers mounted under <ws>/mesh/layers/."""
    return _mount_children(ws_root, "mesh", "layers")


def _mount_single(ws_root, *rel_parts):
    """Real path of the single mount at <ws>/<rel_parts> (e.g. mesh/mcp), or
    None. Every parent directory must be a real directory."""
    current = ws_root
    for name in rel_parts[:-1]:
        current = os.path.join(current, name)
        if os.path.islink(current) or not os.path.isdir(current):
            return None
    mount = os.path.join(current, rel_parts[-1])
    if not os.path.isdir(mount):
        return None
    real = os.path.realpath(mount)
    return real if acceptable_mount(real, ws_root) else None


def mount_roots(ws_root):
    """Real paths of every repo the workspace mounts: projects/<name>,
    mesh/layers/<name> and mesh/mcp. Duplicates and overlaps are fine."""
    roots = _mount_children(ws_root, "projects")
    roots.extend(layer_roots(ws_root))
    mcp = _mount_single(ws_root, "mesh", "mcp")
    if mcp:
        roots.append(mcp)
    return _dedupe(roots)


def _claude_projects_dir():
    return os.path.realpath(os.path.join(_home(), ".claude", "projects"))


def scratchpad_root(payload):
    """The session scratchpad, exactly as the hook payload names it.

    Claude Code sends ``scratchpad_dir`` when the session has one; subagents
    receive their parent's. It must be an absolute, existing, real directory
    (not a symlink). Without the field there is no scratchpad root: the guard
    does not guess it from /tmp/claude-<uid>/, which also holds harness state.
    """
    sp = payload.get("scratchpad_dir")
    if not isinstance(sp, str) or not sp or "\x00" in sp or not os.path.isabs(sp):
        return None
    if os.path.islink(sp) or not os.path.isdir(sp):
        return None
    real = os.path.realpath(sp)
    if os.path.dirname(real) == real or is_under(_home(), real):
        return None  # a disk root or a folder containing $HOME is no scratchpad
    return real


def memory_root(payload):
    """``dirname(transcript_path)/memory``: this project's auto-memory.

    Only when ``transcript_path`` is a non-empty absolute path whose memory
    folder lies under ``~/.claude/projects/``."""
    tp = payload.get("transcript_path")
    if not isinstance(tp, str) or not tp or "\x00" in tp or not os.path.isabs(tp):
        return None
    mem = os.path.realpath(os.path.join(os.path.dirname(tp), "memory"))
    projects = _claude_projects_dir()
    if mem == projects or not is_under(mem, projects):
        return None
    return mem


def _looks_like_project_memory(real):
    """True for ``~/.claude/projects/<slug>/memory/...``."""
    projects = _claude_projects_dir()
    if not is_under(real, projects):
        return False
    rel = _rel_parts(real, projects)
    return len(rel) >= 3 and rel[1] == "memory"


def tmp_roots():
    """Plain temp directories. ``MAICELIUM_TMP_ROOTS`` (os.pathsep-separated)
    replaces the defaults; the tests use it to keep their own tmp_path, which
    lives under the system temp dir, out of the perimeter."""
    override = os.environ.get("MAICELIUM_TMP_ROOTS")
    if override is not None:
        candidates = [p for p in override.split(os.pathsep) if p]
    else:
        candidates = [tempfile.gettempdir()]
        if os.name != "nt":
            candidates += ["/tmp", "/private/tmp"]
    return _dedupe([os.path.realpath(p) for p in candidates if os.path.isabs(p)])


def in_plain_tmp(real):
    """Inside a plain temp dir, but not under any ``claude-*`` folder there:
    ``/tmp/claude-<uid>/`` holds task output and other harness state, and only
    the session's own scratchpad is writable inside it."""
    inside = False
    for t in tmp_roots():
        if real == t or not is_under(real, t):
            continue
        rel = _rel_parts(real, t)
        if rel and rel[0].startswith("claude-"):
            return False
        inside = True
    return inside


def compute_roots(ws_root, payload):
    """Real paths under which writes are allowed.

    - the workspace itself;
    - every mounted repo (``mount_roots``, after ``acceptable_mount``);
    - Claude Code's plan directory ``~/.claude/plans``;
    - this project's auto-memory (``memory_root``);
    - the session scratchpad (``scratchpad_root``).

    Plain temp directories are checked separately (``in_plain_tmp``) because
    they carry an exclusion.
    """
    roots = [os.path.realpath(ws_root)]
    roots.extend(mount_roots(ws_root))
    roots.append(os.path.realpath(os.path.join(_home(), ".claude", "plans")))
    for extra in (memory_root(payload), scratchpad_root(payload)):
        if extra:
            roots.append(extra)
    return _dedupe(roots)


def _reflection_targets(ws_root):
    """Real paths a layer reflection may legitimately resolve into."""
    return _dedupe(
        [os.path.realpath(os.path.join(ws_root, "mesh", "layers"))] + layer_roots(ws_root)
    )


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
                f"Protected file: {base}. Environment files may contain secrets, "
                f"which must not pass through the agent. Write a template instead "
                f"(.env.example, .sample or .template), or ask the user to edit it."
            )
        )
    if base in LOCKFILES:
        out.append(
            deny(f"Protected file: {base} is a lockfile. Use the package manager to update it.")
        )
    if len(parts) >= 2 and parts[-2] == ".claude" and fnmatch.fnmatchcase(base, "settings*.json"):
        out.append(
            ask(
                f"Sensitive file: .claude/{base} holds an agent's permissions and "
                f"hooks. Confirm only if you asked for this change."
            )
        )
    if base == ".sops.yaml":
        out.append(
            ask(
                "Sensitive file: .sops.yaml decides which keys can decrypt the "
                "secrets. Confirm only if you asked for this change."
            )
        )
    if base == "kubeconfig" or base.endswith(KEY_MATERIAL_SUFFIXES):
        out.append(
            ask(
                f"Sensitive file: {base} looks like key or cluster credential "
                f"material; overwriting it can be destructive. Confirm only if "
                f"you asked for this change."
            )
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
    if _is_guard_file(rel):
        out.append(
            ask(
                f"Guard file: {shown} enforces these write and Bash rules. "
                f"Confirm only if you asked for this change."
            )
        )
    return out


def _is_guard_file(rel):
    """bin/hooks/**/*.py, bin/py.sh and bin/py.cmd of the workspace (#44)."""
    if rel[:2] == ["bin", "hooks"] and len(rel) > 2 and rel[-1].endswith(".py"):
        return True
    return rel in (["bin", "py.sh"], ["bin", "py.cmd"])


def _stale_reflection(lexical, real, ws_root):
    ws_lex = os.path.abspath(ws_root)
    if not is_under(lexical, ws_lex):
        return []
    rel = _rel_parts(lexical, ws_lex)
    if not any(tuple(rel[: len(p)]) == p and len(rel) > len(p) for p in _REFLECTION_PREFIXES):
        return []
    if any(is_under(real, r) for r in _reflection_targets(ws_root)):
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
        return deny("Blocked: hook input has no tool_input object. This is a guard input error; retry the tool call.", PERIMETER)
    path = target_path(tool_name, tool_input)
    if not isinstance(path, str) or not path:
        return deny("Blocked: hook input has no file path to check.", PERIMETER)
    # Reject unrepresentable paths up front instead of relying on realpath to
    # raise: on Windows ntpath.realpath swallows the NUL ValueError and returns
    # the path unchanged.
    if "\x00" in path:
        return deny("Blocked: file path contains a NUL byte.", PERIMETER)
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return deny("Blocked: file path is not valid Unicode (lone surrogate).", PERIMETER)
    if not os.path.isabs(path):
        return deny(f"Blocked: file path '{path}' is not absolute.", PERIMETER)

    lexical = os.path.abspath(path)
    real = os.path.realpath(path)

    payload = payload if isinstance(payload, dict) else {}
    roots = compute_roots(ws_root, payload)
    if not (any(is_under(real, r) for r in roots) or in_plain_tmp(real)):
        if memory_root(payload) is None and _looks_like_project_memory(real):
            # No transcript_path to tell which project's memory this is.
            return strictest(
                [
                    ask(
                        "Project memory write without transcript_path in the "
                        "hook input: confirm this is the current project's memory."
                    )
                ]
                + check_names(lexical, real, ws_root)
            )
        return deny(
            f"Blocked: file_path '{path}' is outside the workspace and its "
            f"mounted repos (resolves to '{real}'). To work on that repo, mount "
            f"it with `mai add <name> <path>` (or `mai add-layer <name> <path>`); "
            f"for scratch output, write to the session scratchpad.",
            PERIMETER,
        )

    return strictest(check_names(lexical, real, ws_root))
