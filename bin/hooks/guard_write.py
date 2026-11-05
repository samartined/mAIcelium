#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit, MultiEdit and NotebookEdit.

Reads the Claude Code hook JSON from stdin and delegates the decision to
``_policy.decide`` (see that module for the pipeline and the rules).

Output follows the current hook contract: on deny/ask it prints
``{"hookSpecificOutput": {"permissionDecision": ...}}`` and exits 0; on allow
it prints nothing.

FAILS CLOSED: malformed input or any unexpected exception produces a deny with
the reason, and the failure is logged to ``.claude/hook-failures.log``.
"""
import json
import os
import sys

_HOOK = "guard_write"


def _deny_raw(reason):
    """Deny without relying on _policy (used when it cannot be loaded)."""
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


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _policy

    ws_root = _policy.workspace_root(__file__)
    try:
        data = json.loads(sys.stdin.read())
    except ValueError as e:
        _policy.log_failure(ws_root, _HOOK, f"stdin-parse-error: {e}")
        _policy.emit(_policy.deny(f"{_HOOK}: invalid hook input (not JSON); refusing."))
        return
    if not isinstance(data, dict):
        _policy.log_failure(ws_root, _HOOK, "stdin-not-object")
        _policy.emit(_policy.deny(f"{_HOOK}: invalid hook input (not an object); refusing."))
        return

    tool_name, tool_input = data.get("tool_name"), data.get("tool_input")
    if isinstance(tool_input, dict) and not _policy.target_path(tool_name, tool_input):
        # A runner whose Write payload has no file_path/notebook_path (e.g. a
        # different agent environment importing these hooks). Log the shape,
        # never the values (they can hold file contents), then deny.
        _policy.log_failure(
            ws_root,
            _HOOK,
            f"payload-without-path tool_name={tool_name!r} "
            f"tool_input_keys={sorted(tool_input)} "
            f"event={data.get('hook_event_name')!r}",
        )
        _policy.emit(
            _policy.deny(
                f"Blocked: {_HOOK} got a payload without a file path "
                f"(no file_path or notebook_path in tool_input; keys: "
                f"{sorted(tool_input)}). See issue #49."
            )
        )
        return

    decision = _policy.decide(tool_name, tool_input, data, ws_root)
    _policy.emit(decision)


def main():
    try:
        _run()
    except Exception as e:  # noqa: BLE001 - fail closed on anything unexpected
        reason = f"{_HOOK} crashed: {type(e).__name__}: {e}"
        try:
            import _policy

            _policy.log_failure(_policy.workspace_root(__file__), _HOOK, reason)
        except Exception:  # noqa: BLE001
            pass
        _deny_raw(
            f"Blocked: {reason}. Refusing as a safety measure. The details are in "
            f".claude/hook-failures.log; report it to the user."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
