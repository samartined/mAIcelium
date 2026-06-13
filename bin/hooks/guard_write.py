#!/usr/bin/env python3
"""PreToolUse hook: protect sensitive and auto-generated files from Write/Edit.

Reads Claude Code hook JSON from stdin. Outputs block decision or exits 0
(allow). Fail-open if stdin is malformed; logged to .claude/hook-failures.log
for diagnosis. Fail-CLOSED if file_path is cross-drive (Windows).
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
    # bin/hooks/guard_write.py -> root is 2 levels up from the file
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
            f.write(f"{ts} guard_write {reason}\n")
    except OSError:
        pass


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _resolve_real_for_layer_check(file_path):
    """Return os.path.realpath for an existing file or its nearest existing
    ancestor (joined with the missing tail components). Mirrors the bash logic
    in guard-write.sh so a not-yet-created reflection still reports a sensible
    realpath.
    """
    if os.path.exists(file_path) or os.path.islink(file_path):
        return os.path.realpath(file_path)
    # Walk up to first existing ancestor
    parent = os.path.dirname(file_path)
    tail = [os.path.basename(file_path)]
    while parent and not os.path.exists(parent) and parent != os.path.dirname(parent):
        tail.insert(0, os.path.basename(parent))
        parent = os.path.dirname(parent)
    if not parent:
        return file_path
    real_parent = os.path.realpath(parent)
    return os.path.join(real_parent, *tail)


def _is_under_any_layer(file_path, root):
    """True if resolving file_path traverses through any mesh/layers/<name>/.

    Walks path components one at a time, resolving each symlink with
    readlink (not realpath) so that intermediate targets that land inside
    mesh/layers/ are detected before the chain is fully flattened.
    Protects against cycles with a step counter (max 64 resolutions).
    """
    layers_root = os.path.normpath(os.path.join(root, "mesh", "layers"))
    layers_root_real = os.path.realpath(layers_root)

    def _inside_layers(path):
        p = os.path.normpath(path)
        if p == layers_root or p.startswith(layers_root + os.sep):
            return True
        r = os.path.realpath(path)
        return r == layers_root_real or r.startswith(layers_root_real + os.sep)

    # Walk file_path component by component, resolving each symlink
    # encountered without collapsing the whole chain at once.
    parts = os.path.normpath(file_path).split(os.sep)
    current = os.sep
    steps = 0
    for part in parts:
        if not part:
            continue
        current = os.path.join(current, part)
        if steps > 64:
            return False
        if os.path.islink(current):
            steps += 1
            link_target = os.readlink(current)
            if not os.path.isabs(link_target):
                link_target = os.path.normpath(
                    os.path.join(os.path.dirname(current), link_target)
                )
            if _inside_layers(link_target):
                return True
            current = link_target
    return False


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

    file_path = tool_input.get("file_path", "")
    if not isinstance(file_path, str) or not file_path:
        sys.exit(0)

    root = _get_root()
    basename = os.path.basename(file_path)

    # Cross-drive fail-CLOSED (Windows: E:\ vs C:\ raises ValueError)
    try:
        rel = os.path.relpath(file_path, root)
    except ValueError as e:
        _log_failure(f"cross-drive: {e}")
        _block(
            f"Blocked: file_path '{file_path}' is outside the workspace "
            f"(cross-drive). Refusing as a safety measure."
        )

    rel_path_posix = rel.replace("\\", "/")

    # Layer-managed reflections. Paths under
    # mesh/skills/{_common,_domains,_clients}/ and
    # mesh/rules/{_domains,_clients}/ are reflections of content that lives
    # in mesh/layers/<layer>/. When the reflection is properly symlinked,
    # _is_under_any_layer resolves through the layer chain - allow.
    # Otherwise, check if realpath lands directly inside mesh/layers/.
    # This check runs BEFORE the outside-workspace guard so that legitimate
    # writes to external layers are not accidentally blocked.
    layer_pattern = (
        r"^mesh/(skills/(_common|_domains|_clients)|"
        r"rules/(_domains|_clients))/"
    )
    layer_path_matched = bool(re.match(layer_pattern, rel_path_posix))
    if layer_path_matched:
        via_layer = _is_under_any_layer(file_path, root)
        if not via_layer:
            # Fallback: check whether realpath resolves directly inside layers/
            real = _resolve_real_for_layer_check(file_path)
            layers_root = os.path.realpath(os.path.join(root, "mesh", "layers"))
            try:
                real_rel = os.path.relpath(real, layers_root)
                inside_layers = not real_rel.startswith("..") and not os.path.isabs(real_rel)
            except ValueError:
                inside_layers = False
            if not inside_layers:
                _block(
                    f"Layer-managed path: {rel_path_posix} is a stale "
                    f"reflection, not a symlink to a source-of-truth layer. "
                    f"Edit the canonical file under mesh/layers/<layer>/ and "
                    f"run bin/sync_symlinks.py. Current realpath: {real}"
                )
        # Layer check passed: skip the outside-workspace guard below
    else:
        # Fail-CLOSED if the path escapes the workspace (absolute outside root,
        # or relative with ..). This protects against /etc/cron.d/foo,
        # /root/.ssh/authorized_keys, and similar out-of-workspace writes.
        root_real = os.path.realpath(root)
        file_real = os.path.realpath(file_path)
        # Exception: Claude Code's own plan directory (~/.claude/plans/) lives
        # outside the workspace but is legitimate harness state the agent must
        # be able to write (plan mode). Scoped to plans/ only -- the global
        # ~/.claude/settings.json stays protected.
        claude_plans = os.path.realpath(os.path.expanduser("~/.claude/plans"))
        under_claude_plans = (
            file_real == claude_plans
            or file_real.startswith(claude_plans + os.sep)
        )
        outside = (not under_claude_plans) and (
            rel_path_posix.startswith("..")
            or (
                os.path.isabs(file_path)
                and not (
                    file_real == root_real
                    or file_real.startswith(root_real + os.sep)
                )
            )
        )
        if outside:
            _block(
                f"Blocked: file_path '{file_path}' is outside the workspace. "
                f"Refusing write as a safety measure."
            )

    # Environment files (secrets): .env or .env.*
    if basename == ".env" or basename.startswith(".env."):
        _block(
            f"Protected file: {basename}. "
            f"Environment files may contain secrets."
        )

    # Git internals
    if re.search(r"^\.git/|/\.git/", rel_path_posix):
        _block("Protected path: .git/ internals must not be modified by agents.")

    # Auto-generated workspace files
    if basename in ("WORKSPACE.md", "mAIcelium.code-workspace"):
        _block(
            f"Protected file: {rel_path_posix} is auto-generated. "
            f"Use bin/ scripts to modify it."
        )

    if rel_path_posix == ".claude/projects-context.md":
        _block(
            "Protected file: projects-context.md is auto-generated by "
            "sync_symlinks.py."
        )

    # Agent config (prevent self-modification of permissions)
    if re.match(r"^\.claude/settings.*\.json$", rel_path_posix):
        _block(
            f"Protected file: {rel_path_posix}. "
            f"Agent must not modify its own permissions."
        )

    # Auto-generated IDE dotfolders
    if re.match(r"^\.(cursor|agents|antigravity)/", rel_path_posix):
        _block(
            f"Protected path: {rel_path_posix} is auto-generated via "
            f"symlinks. Write to mesh/ instead."
        )

    # Lockfiles
    if basename in (
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
    ):
        _block(
            f"Protected file: {basename} is a lockfile. "
            f"Use the package manager to update it."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
