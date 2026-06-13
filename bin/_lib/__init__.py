"""mAIcelium shared library — Python port of bin/_lib.sh.

Public API (import via `from _lib.<module> import <name>`):

- conventions.load_conventions(root) -> dict
- workspace.load_workspace_section(root, section) -> list | dict | None
- workspace.WorkspaceParseError
"""
