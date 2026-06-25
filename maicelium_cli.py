#!/usr/bin/env python3
"""maicelium_cli.py -- the `mai` CLI router.

Single top-level module at repo root. Dispatches subcommands to bin/ and
mesh/commands/scripts/ via subprocess (NEVER imports them).

Public surface:
  __version__         -- single source of truth; consumed by pyproject dynamic attr
  VERBS               -- ordered dict: canonical verb -> {rel_path, aliases, summary}
  ALIASES             -- flat map: alias -> canonical verb
  resolve_root_for_cli(args, env, cwd, file) -> str
  dispatch(verb, args, root) -> int
  main(argv=None) -> int
"""
import os
import subprocess
import sys
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# VERBS registry — canonical verb -> {rel_path, aliases, summary}
# Ordering follows the spec command_surface section.
# ---------------------------------------------------------------------------
VERBS = {
    "init": {
        "rel_path": "bin/init.py",
        "aliases": [],
        "summary": "Scaffold a new mAIcelium workspace",
    },
    "add": {
        "rel_path": "bin/add_project.py",
        "aliases": ["add-project", "add_project"],
        "summary": "Add a project symlink (deterministic bin/ writer)",
    },
    "remove": {
        "rel_path": "bin/remove_project.py",
        "aliases": ["remove-project", "remove_project", "rm"],
        "summary": "Remove a project symlink",
    },
    "sync": {
        "rel_path": "bin/sync_symlinks.py",
        "aliases": ["sync-symlinks", "sync_symlinks"],
        "summary": "Sync workspace symlinks (check/fix drift)",
    },
    "separate-git": {
        "rel_path": "bin/separate_git.py",
        "aliases": ["separate_git", "git-separate"],
        "summary": "Separate a project's git history",
    },
    "add-mcp": {
        "rel_path": "bin/add_mcp_source.py",
        "aliases": ["add-mcp-source", "add_mcp_source"],
        "summary": "Mount an external MCP definitions directory",
    },
    "remove-mcp": {
        "rel_path": "bin/remove_mcp_source.py",
        "aliases": ["remove-mcp-source", "remove_mcp_source"],
        "summary": "Unmount the current MCP source",
    },
    "add-layer": {
        "rel_path": "bin/add_mesh_layer.py",
        "aliases": ["add-mesh-layer", "add_mesh_layer"],
        "summary": "Add a mesh layer",
    },
    "remove-layer": {
        "rel_path": "bin/remove_mesh_layer.py",
        "aliases": ["remove-mesh-layer", "remove_mesh_layer"],
        "summary": "Remove a mesh layer",
    },
    "set-flag": {
        "rel_path": "bin/set_project_flag.py",
        "aliases": ["set-project-flag", "set_project_flag"],
        "summary": "Set a project flag",
    },
    "list": {
        "rel_path": "mesh/commands/scripts/list_projects.py",
        "aliases": ["list-projects", "list_projects", "ls"],
        "summary": "List all linked projects",
    },
    "health": {
        "rel_path": "mesh/commands/scripts/project_health.py",
        "aliases": ["project-health", "project_health"],
        "summary": "Run health checks across all linked projects",
    },
}

# ---------------------------------------------------------------------------
# ALIASES flat map: alias -> canonical verb
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {}
for _verb, _spec in VERBS.items():
    for _alias in _spec["aliases"]:
        ALIASES[_alias] = _verb


def _resolve_version() -> str:
    """Return version: prefer importlib.metadata (after editable install), fall back to __version__."""
    try:
        from importlib.metadata import version as _meta_version
        return _meta_version("maicelium")
    except Exception:
        return __version__


def build_version() -> str:
    """Return the version string for --version output (unit-testable, no side effects)."""
    return f"mai {_resolve_version()}"


def build_help() -> str:
    """Return the full help text (unit-testable, no side effects)."""
    lines = [
        "mai -- mAIcelium CLI router",
        "",
        "Usage: mai [--root <path>] [--version | -V] [--help | -h | help]",
        "       mai <verb> [args...]",
        "",
        "Global options:",
        "  --root <path>   Override workspace root (else uses MAICELIUM_ROOT or auto-detect)",
        "  --version, -V   Print version and exit",
        "  --help, -h      Print this help and exit",
        "",
        "Commands:",
    ]
    for verb, spec in VERBS.items():
        aliases_str = ""
        if spec["aliases"]:
            aliases_str = f"  (aliases: {', '.join(spec['aliases'])})"
        lines.append(f"  {verb:<16} {spec['summary']}{aliases_str}")
    lines.append("")
    lines.append("All arguments after the verb are forwarded verbatim to the target script.")
    lines.append("Run 'mai <verb> --help' for verb-specific help.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

_WORKSPACE_MARKERS = ("bin/_bootstrap.py", "mesh")


def _is_workspace_root(path: Path) -> bool:
    """True if path contains bin/_bootstrap.py AND mesh/ (the workspace marker pair)."""
    return (path / "bin" / "_bootstrap.py").exists() and (path / "mesh").exists()


def resolve_root_for_cli(
    args: list[str],
    env: dict[str, str],
    cwd: str,
    file: str,
) -> str:
    """Resolve the workspace root using the layered precedence ladder.

    Precedence (first match wins):
      1. --root <path> on args (validated: must exist)
      2. MAICELIUM_ROOT in env (passed through verbatim -- no existence check;
         asymmetric vs --root, documented as doubt #4)
      3. Upward cwd-walk for a dir containing bin/_bootstrap.py AND mesh/
         (nearest ancestor wins -- first-match-wins is deterministic)
      4. maicelium_cli.__file__ directory (fallback for editable install)

    Raises SystemExit(2) if --root is provided but does not exist.
    """
    # Layer 1: --root flag
    i = 0
    while i < len(args):
        if args[i] == "--root" and i + 1 < len(args):
            root_path = args[i + 1]
            if not os.path.isdir(root_path):
                _print_error(
                    f"Error: --root path does not exist or is not a directory: {root_path!r}\n"
                    "Set MAICELIUM_ROOT or use --root <valid-workspace-path>."
                )
                raise SystemExit(2)
            # Normalize to absolute path so dispatch exports a stable absolute cwd
            # and MAICELIUM_ROOT to the child. Without this, a relative --root like
            # './ws' is valid in the parent but double-resolves in the child (the child
            # sees cwd=./ws and re-resolves MAICELIUM_ROOT=./ws relative to that new
            # cwd, producing ws/ws). os.path.abspath resolves against the parent's cwd.
            return os.path.abspath(root_path)
        i += 1

    # Layer 2: MAICELIUM_ROOT env, returned verbatim with NO marker validation
    # (matches platform.resolve_root() line 20). The resolver does not check
    # existence here; main() validates that the FINAL resolved root exists before
    # dispatching, so a bogus MAICELIUM_ROOT gets an actionable error instead of a
    # confusing subprocess FileNotFoundError (resolves the former doubt #4 toward
    # "validate existence, but not the workspace marker").
    env_root = env.get("MAICELIUM_ROOT", "")
    if env_root:
        return env_root

    # Layer 3: upward cwd-walk for bin/_bootstrap.py + mesh/ marker
    # First-match-wins selects the NEAREST ancestor (inner wins over outer
    # in nested multi-workspace trees -- the mAIcelium design use case).
    current = Path(cwd).resolve()
    while True:
        if _is_workspace_root(current):
            return str(current)
        parent = current.parent
        if parent == current:
            # Reached filesystem root with no marker found
            break
        current = parent

    # Layer 4: maicelium_cli.__file__ dir fallback -- ONLY if it is a real workspace.
    # For an editable install, maicelium_cli.py lives next to bin/ and mesh/, so this
    # resolves the repo root. A severed (non-editable) wheel or a stray copy has no
    # marker here: rather than return a non-workspace dir and let the child fail with a
    # confusing "No projects directory found" (exit 0), report an actionable error.
    fallback = Path(file).parent
    if _is_workspace_root(fallback):
        return str(fallback)
    _print_error(
        "Error: could not locate a mAIcelium workspace. Run mai from inside a "
        "workspace, set MAICELIUM_ROOT=<path>, or pass --root <path>."
    )
    raise SystemExit(2)


def _print_error(msg: str) -> None:
    """Print an error message to stderr using only ASCII/cp1252-safe characters."""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(verb: str, args: list[str], root: str) -> int:
    """Dispatch verb to its target script via subprocess.

    The script is resolved relative to the maicelium_cli.py installation
    directory (where the scripts actually live), NOT relative to the workspace
    root passed as `root`. This allows the workspace root (MAICELIUM_ROOT) to
    point at a separate directory (e.g. a tmp test workspace) while the scripts
    themselves are in the real installation tree.

    The child env inherits the parent env plus MAICELIUM_ROOT=root (the workspace
    root), and cwd is also set to root. This means the child scripts use `root`
    to find projects/, but the scripts are invoked from the real installation.

    Args are forwarded VERBATIM (never argparsed by the router).
    Streams are INHERITED (not captured) so child _safe_stdout/emoji handling
    and interactive output are preserved. PYTHONIOENCODING is NEVER force-set.

    Returns the child returncode. A child killed by a signal (negative POSIX
    returncode) is mapped to the conventional 128+signum so the shell exit status
    is meaningful; all non-signal codes pass through verbatim (never remapped).
    """
    spec = VERBS[verb]
    # Resolve script path from the directory where maicelium_cli.py lives
    # (the real installation, not the workspace root which may be a tmp test dir).
    install_dir = Path(__file__).parent
    script_path = str(install_dir / spec["rel_path"])
    cmd = [sys.executable, script_path, *args]

    # Build child env: parent env + MAICELIUM_ROOT set to workspace root
    child_env = os.environ.copy()
    child_env["MAICELIUM_ROOT"] = str(root)

    result = subprocess.run(
        cmd,
        cwd=str(root),
        env=child_env,
        check=False,
    )
    rc = result.returncode
    # On POSIX a signal-killed child returns a negative code (e.g. -2 for SIGINT);
    # returning it verbatim makes the shell wrap it to garbage (e.g. -2 -> 254).
    # Map to the conventional 128+signum (SIGINT -> 130). Positive codes pass through.
    if rc < 0:
        return 128 + (-rc)
    return rc


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an integer exit code (never calls sys.exit).

    Arg parsing rules (CRITICAL -- load-bearing for several tests):
    - Only --root/--version/-V/--help/-h are consumed BEFORE the verb.
    - The verb is the FIRST non-option token (not starting with -).
    - Everything AFTER the verb is forwarded VERBATIM to the child.
    - Verb-level flags (--check-only, --help, etc.) are NEVER parsed by the router.
    """
    if argv is None:
        argv = sys.argv[1:]

    # ---- Pre-verb flag parsing (manual, not argparse) ----
    # We walk tokens, consuming --root/--version/-V/--help/-h.
    # The moment we see the first non-option token, that is the verb.
    root_override: str | None = None
    i = 0
    while i < len(argv):
        token = argv[i]

        if token in ("--version", "-V"):
            print(build_version())
            return 0

        if token in ("--help", "-h", "help"):
            print(build_help())
            return 0

        if token == "--root":
            if i + 1 >= len(argv):
                _print_error("Error: --root requires a path argument. See 'mai --help'.")
                return 2
            root_override = argv[i + 1]
            i += 2
            continue

        # First non-option token is the verb
        if not token.startswith("-"):
            verb_token = token
            verb_args = argv[i + 1:]
            break

        # Unknown mai-level option before the verb is a usage error (exit 2).
        # Only --root/--version/-V/--help/-h/help are valid before the verb;
        # verb-level flags come AFTER the verb and are forwarded verbatim. Without
        # this, an unknown global flag was silently swallowed (adversarial finding).
        _print_error(
            f"Error: unknown option '{token}' before a command. Run 'mai --help'."
        )
        return 2
    else:
        # No verb found (bare `mai` or only options consumed)
        print(build_help())
        return 0

    # ---- Resolve verb ----
    canonical_verb = VERBS.get(verb_token) and verb_token
    if canonical_verb is None:
        canonical_verb = ALIASES.get(verb_token)
    if canonical_verb is None:
        _print_error(
            f"Error: unknown command '{verb_token}'. Run 'mai --help' for a list of commands."
        )
        return 2

    # ---- Resolve root ----
    # Build the resolver's arg list from the PRE-VERB --root only. verb_args are
    # NEVER scanned for --root: a post-verb --root is the child script's own flag
    # and is forwarded verbatim (fixes the router double-handling a verb-level
    # --root -- both hijacking routing and forwarding it).
    resolve_args: list[str] = []
    if root_override is not None:
        resolve_args = ["--root", root_override]
    resolve_args.append(verb_token)

    try:
        root = resolve_root_for_cli(
            args=resolve_args,
            env=dict(os.environ),
            cwd=os.getcwd(),
            file=__file__,
        )
    except SystemExit:
        raise
    except Exception as exc:
        _print_error(f"Error resolving workspace root: {exc}")
        return 2

    # Validate the resolved root exists before dispatching. MAICELIUM_ROOT is
    # trusted verbatim by the resolver (UNIT-10), so a bogus value would otherwise
    # make subprocess.run(cwd=root) raise a confusing FileNotFoundError. Give an
    # actionable message instead. (--root existence is already validated upstream.)
    if not os.path.isdir(root):
        _print_error(
            f"Error: workspace root does not exist: {root!r}\n"
            "Set MAICELIUM_ROOT to a valid workspace or pass --root <path>."
        )
        return 2

    # ---- Dispatch ----
    try:
        return dispatch(canonical_verb, verb_args, root)
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError as exc:
        # Defensive: the root existence check above normally prevents this, but a
        # race (root removed mid-run) or a missing script would still land here.
        _print_error(
            f"Error: workspace root or target script not found: {exc}. "
            "Check MAICELIUM_ROOT / --root."
        )
        return 2
    except Exception as exc:
        _print_error(f"Error dispatching '{canonical_verb}': {exc}")
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
