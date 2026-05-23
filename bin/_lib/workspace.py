"""Unified parser for WORKSPACE.md sections.

Replaces three ad-hoc parsers in bin/_lib.sh:
- _load_mesh_layers   -> load_workspace_section(root, "mesh_layers")
- _load_mcp_source    -> load_workspace_section(root, "mcp_source")
- _load_no_inline_projects -> load_workspace_section(root, "no_inline_projects")

The parser is YAML-light: top-level keys end with ':', list items start
with '- name:', and section ends at the next top-level key. No PyYAML
dependency — keeps cross-platform install footprint zero.
"""
import os
import sys

KNOWN_SECTIONS = ("mesh_layers", "mcp_source", "no_inline_projects")


class WorkspaceParseError(RuntimeError):
    """Raised on malformed WORKSPACE.md when strict mode is on."""


def _is_top_level_key(line, stripped):
    """True if line starts a new top-level key (no indent, ends with ':')."""
    return (
        bool(line)
        and not line.startswith(" ")
        and not line.startswith("-")
        and stripped.endswith(":")
    )


def _read_workspace(root):
    """Return (lines, exists) for WORKSPACE.md at root. Missing file -> ([], False)."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.isfile(wf):
        return [], False
    with open(wf) as f:
        return f.read().splitlines(), True


def _parse_path_value(raw, root):
    """Expand ~ and resolve relative paths against root, normpath."""
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        expanded = os.path.join(root, expanded)
    return os.path.normpath(expanded)


def _parse_mesh_layers(lines, root):
    """Return list of layer dicts: [{name, path?, client?, repo?}, ...]."""
    layers = []
    in_section = False
    current = None

    for line in lines:
        stripped = line.strip()

        if stripped == "mesh_layers:":
            in_section = True
            continue
        if not in_section:
            continue
        if _is_top_level_key(line, stripped):
            if current:
                layers.append(current)
            break

        if stripped.startswith("- name:"):
            if current:
                layers.append(current)
            current = {"name": stripped.split(":", 1)[1].strip()}
        elif stripped.startswith("path:") and current is not None:
            current["path"] = _parse_path_value(stripped.split(":", 1)[1].strip(), root)
        elif stripped.startswith("client:") and current is not None:
            current["client"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("repo:") and current is not None:
            current["repo"] = stripped.split(":", 1)[1].strip()

    if current and current not in layers:
        layers.append(current)
    return layers


def _parse_mcp_source(lines, root):
    """Return {path, repo?} dict or None if no path registered."""
    source = {}
    in_section = False

    for line in lines:
        stripped = line.strip()

        if stripped == "mcp_source:":
            in_section = True
            continue
        if not in_section:
            continue
        if _is_top_level_key(line, stripped):
            break

        if stripped.startswith("path:"):
            source["path"] = _parse_path_value(stripped.split(":", 1)[1].strip(), root)
        elif stripped.startswith("repo:"):
            source["repo"] = stripped.split(":", 1)[1].strip()

    return source if source.get("path") else None


def _parse_no_inline_projects(lines):
    """Return list of project names with context_inline: false.

    NOTE: bin/_lib.sh has a latent bug where, when a boundary key (e.g.
    `mesh_layers:`) immediately follows the last `- name:` entry, the same
    name is appended twice (once at the boundary, once at the post-loop flush).
    This Python port deduplicates the result instead of replicating the bug —
    a deviation from byte-parity with bash but a fix that is functionally
    safer (downstream consumers used `grep -qx`, which is idempotent, so the
    bug was harmless but ugly).
    """
    result = []
    in_section = False
    current_name = None
    current_no_inline = False

    def _flush():
        if current_name and current_no_inline and current_name not in result:
            result.append(current_name)

    for line in lines:
        stripped = line.strip()

        if stripped == "projects:":
            in_section = True
            continue
        if not in_section:
            continue
        if _is_top_level_key(line, stripped):
            _flush()
            break

        if stripped.startswith("- name:"):
            _flush()
            current_name = stripped.split(":", 1)[1].strip()
            current_no_inline = False
        elif stripped.startswith("context_inline:") and current_name is not None:
            val = stripped.split(":", 1)[1].strip().lower()
            current_no_inline = val == "false"

    _flush()
    return result


def load_workspace_section(root, section, warn_on_empty=True):
    """Load one section of WORKSPACE.md.

    section: one of "mesh_layers", "mcp_source", "no_inline_projects".
    warn_on_empty: emit stderr warning if WORKSPACE.md is non-empty but
                   the parser returned empty result (likely malformed).

    Returns:
        - mesh_layers:        list[dict]   (may be empty)
        - mcp_source:         dict | None  (None if no path)
        - no_inline_projects: list[str]    (may be empty)
    """
    if section not in KNOWN_SECTIONS:
        raise ValueError(f"Unknown section: {section!r}. Known: {KNOWN_SECTIONS}")

    lines, exists = _read_workspace(root)

    if section == "mesh_layers":
        result = _parse_mesh_layers(lines, root)
    elif section == "mcp_source":
        result = _parse_mcp_source(lines, root)
    else:
        result = _parse_no_inline_projects(lines)

    if warn_on_empty and exists and lines:
        empty = (result is None) or (hasattr(result, "__len__") and len(result) == 0)
        marker = f"{section}:"
        if empty and any(ln.strip() == marker for ln in lines):
            print(
                f"⚠️  WORKSPACE.md parser returned empty for section "
                f"'{section}' but the marker is present. Check indentation.",
                file=sys.stderr,
            )

    return result
