"""Unified writer for WORKSPACE.md mutations.

Consolidates the parser+writer logic previously duplicated in 7 mutator
scripts (add_project, remove_project, add_mesh_layer, remove_mesh_layer,
add_mcp_source, remove_mcp_source, set_project_flag).

Each function reads WORKSPACE.md, applies a targeted edit, and writes
back. Empty sections (e.g. `projects:\n` with no items) are preserved.
Top-level boundary detection is shared via _is_top_level_key.

WORKSPACE.md format assumptions:
  - Top-level keys: no indent, end with ':', do not start with '-'
  - List entries start with '- name: <value>'
  - Entry continuation lines start with space or tab
  - A blank line belongs to the current entry when the first non-blank
    line that follows it is indented (lookahead rule from BUG-01 fix)
"""
from __future__ import annotations

import os
import re

from _lib.workspace import _is_top_level_key  # reuse existing helper

WORKSPACE_FILE = "WORKSPACE.md"


# ── Workspace template ───────────────────────────────────────────────────────


def create_workspace_template(root, *, created=None):
    """Create an initial WORKSPACE.md with a standard header. Idempotent.

    If WORKSPACE.md already exists, it is left completely unchanged.

    created: optional ISO 8601 / RFC 3339 timestamp string. When provided,
             a `created: <ts>` line is written before `projects:` so that
             the projects section parser does not confuse it with an entry
             field (the parser stops only at bare `<key>:` lines, not at
             `key: value` lines like `created: <timestamp>`).
    """
    wf = os.path.join(root, WORKSPACE_FILE)
    if os.path.isfile(wf):
        return

    lines = ["# Active workspace", ""]
    if created is not None:
        lines.append(f"created: {created}")
        lines.append("")
    lines.extend(["projects: []", ""])

    _write_content(wf, "\n".join(lines))


# ── Project entries ──────────────────────────────────────────────────────────


def add_project_entry(root, name, path, *, added=None):
    """Add `- name: <name>` under `projects:`. Creates section if missing.

    added: optional ISO 8601 timestamp string. If None, no `added:` field
           is written (caller can decide).

    Matches the logic from add_project._update_workspace_md:
    - If file missing: creates WORKSPACE.md with header + projects section.
    - If `projects: []` found: replaces inline empty list with section.
    - If `projects:` section exists (bare): appends entry at end.
    - Otherwise: appends a new `projects:` section at end.
    """
    wf = os.path.join(root, WORKSPACE_FILE)

    entry_lines = [f"- name: {name}", f"  path: {path}"]
    if added is not None:
        entry_lines.append(f"  added: {added}")
    entry = "\n".join(entry_lines)

    if not os.path.isfile(wf):
        # NOTE: When file is missing the original also writes `created:`.
        # That field is not our responsibility here; callers that need it
        # should pass added= or write it separately.
        content = (
            "# Active workspace\n"
            "\n"
            f"projects:\n{entry}\n"
        )
        _write_content(wf, content)
        return

    content = _read_content(wf)

    if "projects: []" in content:
        content = content.replace("projects: []", "projects:\n" + entry)
    elif _section_exists_bare(content, "projects"):
        # `projects:` exists as a bare section key -> append entry
        content = content.rstrip() + "\n" + entry + "\n"
    else:
        content = content.rstrip() + "\n\nprojects:\n" + entry + "\n"

    _write_content(wf, content)


def remove_project_entry(root, name):
    """Remove the `- name: <name>` entry from `projects:` (and its indented
    continuation, including blank lines that belong to the entry block).

    Blank-line handling (BUG-01): a blank line belongs to the entry when
    the first non-blank line following it is indented. This is tested
    separately in test_remove_project_handles_blank_lines_in_entry.

    Idempotent: if the entry is not found the file is left unchanged.
    """
    wf = os.path.join(root, WORKSPACE_FILE)
    if not os.path.isfile(wf):
        return

    lines = _read_lines(wf)
    out = _remove_entry_block(lines, name)
    _write_lines(wf, out)


def set_project_flag(root, project_name, flag_key, value):
    """Set `<flag_key>: <value>` inside the project entry.

    Insert if missing, update if present.

    Returns (action, error_msg):
      action: "added" | "updated" | None
      error_msg: non-empty string when project not found (file unchanged)

    Matches the logic from set_project_flag._update_flag.
    """
    wf = os.path.join(root, WORKSPACE_FILE)
    if not os.path.isfile(wf):
        return None, f"WORKSPACE.md not found at {wf}"

    lines = _read_lines(wf)

    in_projects = False
    in_target = False
    target_end = None
    flag_line = None
    insert_after = None

    for i, line in enumerate(lines):
        stripped = line.rstrip("\n").strip()

        if stripped == "projects:":
            in_projects = True
            continue

        if not in_projects:
            continue

        raw = line.rstrip("\n")
        # End of projects section
        if _is_top_level_key(raw, stripped):
            if in_target:
                target_end = i
            break

        if stripped.startswith("- name:"):
            entry_name = stripped.split(":", 1)[1].strip()
            if in_target and target_end is None:
                target_end = i
            in_target = (entry_name == project_name)
            if in_target:
                insert_after = i

        if in_target:
            if stripped.startswith(f"{flag_key}:"):
                flag_line = i
            elif stripped and not stripped.startswith("#"):
                insert_after = i

    if not in_target and target_end is None:
        return None, f"project '{project_name}' not found in WORKSPACE.md"

    if flag_line is not None:
        old = lines[flag_line]
        indent = len(old.rstrip("\n")) - len(old.rstrip("\n").lstrip())
        lines[flag_line] = " " * indent + f"{flag_key}: {value}\n"
        action = "updated"
    else:
        indent = 2
        new_line = " " * indent + f"{flag_key}: {value}\n"
        lines.insert(insert_after + 1, new_line)
        action = "added"

    _write_lines(wf, lines)
    return action, ""


# ── Mesh layer entries ───────────────────────────────────────────────────────


def add_layer_entry(root, name, path, *, client=None, repo=None):
    """Add `- name: <name>` under `mesh_layers:`. Creates section if missing.

    If client is None it is omitted from the entry (the caller is
    responsible for defaulting client=name before calling here if needed).

    Returns True if written, False if duplicate detected (file unchanged).

    Matches the logic from add_mesh_layer._update_workspace.
    """
    wf = os.path.join(root, WORKSPACE_FILE)

    if not os.path.isfile(wf):
        # Create a minimal WORKSPACE.md
        content = "# Active workspace\n\nprojects: []\n"
        _write_content(wf, content)

    content = _read_content(wf)

    # Build entry
    entry_lines = [f"- name: {name}", f"  path: {path}"]
    if client is not None:
        entry_lines.append(f"  client: {client}")
    if repo:
        entry_lines.append(f"  repo: {repo}")
    entry = "\n".join(entry_lines)

    # Check for duplicate within mesh_layers section only
    in_layers = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "mesh_layers:":
            in_layers = True
            continue
        if in_layers:
            if _is_top_level_key(line, stripped):
                break
            if stripped == f"- name: {name}":
                print(f"  Warning: Layer '{name}' already exists in WORKSPACE.md")
                return False

    # Insert into mesh_layers section or create it
    if "mesh_layers:" in content:
        lines = content.splitlines()
        insert_at = None
        in_layers = False
        for i, line in enumerate(lines):
            if line.strip() == "mesh_layers:":
                in_layers = True
                continue
            if in_layers:
                if _is_top_level_key(line, line.strip()):
                    insert_at = i
                    break
        if insert_at is None:
            # mesh_layers is the last section
            content = content.rstrip() + "\n" + entry + "\n"
        else:
            lines.insert(insert_at, entry)
            content = "\n".join(lines) + "\n"
    else:
        # Prepend mesh_layers before projects:
        if "projects:" in content:
            content = content.replace("projects:", f"mesh_layers:\n{entry}\n\nprojects:", 1)
        else:
            content = f"mesh_layers:\n{entry}\n\n" + content

    _write_content(wf, content)
    return True


def remove_layer_entry(root, name):
    """Remove the layer entry by name (and its indented continuation).

    Only strips within the `mesh_layers:` section. Blank lines that
    belong to the entry (BUG-01 lookahead rule) are also removed.
    Idempotent: no-op if entry not found.

    Matches the logic from remove_mesh_layer._strip_workspace_entry.
    """
    wf = os.path.join(root, WORKSPACE_FILE)
    if not os.path.isfile(wf):
        return

    lines = _read_lines(wf)
    out = []
    skip = False
    in_layers = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").strip()

        if stripped == "mesh_layers:":
            in_layers = True
            out.append(line)
            i += 1
            continue

        if in_layers:
            # New top-level key terminates the section.
            raw = line.rstrip("\n")
            if _is_top_level_key(raw, stripped):
                in_layers = False
                skip = False
                out.append(line)
                i += 1
                continue

            if stripped == f"- name: {name}":
                skip = True
                i += 1
                continue

            if skip:
                # Indented continuation -> still inside the entry.
                if line.startswith("  "):
                    i += 1
                    continue

                if stripped == "":
                    # Look ahead to the first non-blank line.
                    j = i + 1
                    while j < len(lines) and lines[j].rstrip("\n").strip() == "":
                        j += 1
                    if j < len(lines) and lines[j].startswith("  "):
                        # Blank lines belong to the entry; skip past them.
                        i = j
                        continue
                    # Entry ended; keep the blank separator.
                    skip = False
                    out.append(line)
                    i += 1
                    continue

                # Non-blank, non-indented line: entry has ended.
                skip = False

        out.append(line)
        i += 1

    _write_lines(wf, out)


# ── MCP source block ─────────────────────────────────────────────────────────


def set_mcp_source(root, path, *, repo=None):
    """Set the `mcp_source:` block. Replaces existing block atomically.

    Ordering: mcp_source sits above `projects:` (mesh_layers -> mcp_source
    -> projects). When no mcp_source exists, the block is inserted before
    the first `projects:` line (if any), otherwise appended.

    Matches the logic from add_mcp_source._update_workspace.
    """
    wf = os.path.join(root, WORKSPACE_FILE)

    if not os.path.isfile(wf):
        content = "# Active workspace\n\nprojects: []\n"
        _write_content(wf, content)

    content = _read_content(wf)

    entry_lines = ["mcp_source:", f"  path: {path}"]
    if repo:
        entry_lines.append(f"  repo: {repo}")
    entry = "\n".join(entry_lines)

    lines = content.splitlines()
    new_lines = []
    i = 0
    replaced = False

    while i < len(lines):
        line = lines[i]
        if line.strip() == "mcp_source:":
            replaced = True
            new_lines.extend(entry.splitlines())
            i += 1
            # Consume old block body (indented/blank) until next section or blank sep
            while i < len(lines):
                nxt = lines[i]
                nxt_stripped = nxt.strip()
                if _is_top_level_key(nxt, nxt_stripped):
                    break
                if nxt_stripped == "" and i + 1 < len(lines):
                    new_lines.append(nxt)
                    i += 1
                    break
                i += 1
            continue
        new_lines.append(line)
        i += 1

    if not replaced:
        # Insert mcp_source before projects: (ordering: mesh_layers -> mcp_source -> projects)
        final = []
        inserted = False
        for line in new_lines:
            if not inserted and line.strip() == "projects:":
                final.append(entry)
                final.append("")
                inserted = True
            final.append(line)
        if not inserted:
            final = new_lines + ["", entry, ""]
        new_lines = final

    output = "\n".join(new_lines)
    if not output.endswith("\n"):
        output += "\n"

    _write_content(wf, output)


def unset_mcp_source(root):
    """Strip the `mcp_source:` block entirely. Idempotent.

    Also consumes the trailing blank line that follows the block (if any),
    matching the behaviour of remove_mcp_source._strip_workspace_block.
    """
    wf = os.path.join(root, WORKSPACE_FILE)
    if not os.path.isfile(wf):
        return

    lines = _read_lines(wf)
    out = []
    in_block = False

    for line in lines:
        stripped = line.rstrip("\n").strip()

        if stripped == "mcp_source:":
            in_block = True
            continue

        if in_block:
            raw = line.rstrip("\n")
            # End of block: next top-level key
            if _is_top_level_key(raw, stripped):
                in_block = False
                out.append(line)
                continue
            # Skip indented or blank lines inside the block;
            # a bare blank line also terminates the block.
            if raw.startswith(" ") or not stripped:
                if not stripped:
                    in_block = False
                continue

        out.append(line)

    _write_lines(wf, out)


# ── Internal helpers (private) ───────────────────────────────────────────────


def _read_lines(path):
    """Return file lines as list (with newlines), or [] if file missing."""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def _write_lines(path, lines):
    """Write a list of lines (with newlines) back to path."""
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _read_content(path):
    """Return file contents as a string."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write_content(path, content):
    """Write string content to path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _section_exists_bare(content, section_name):
    """Return True if `section_name:` appears as a bare top-level key."""
    return bool(re.search(rf"^{re.escape(section_name)}:\s*$", content, flags=re.MULTILINE))


def _remove_entry_block(lines, target_name):
    """Remove the `- name: target_name` entry and all its indented continuation,
    including blank lines that belong to the entry block.

    A blank line belongs to the entry when the next non-blank line is indented
    (starts with a space or tab). Once a non-blank, non-indented line follows,
    the entry has ended and the blank separators are kept.

    This is the shared implementation used by remove_project_entry. It operates
    globally (not restricted to a particular section), so callers that need
    section-scoped removal should use remove_layer_entry instead.
    """
    out = []
    skip = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").strip()

        if skip:
            # Indented line -> still inside the entry block.
            if line.startswith(" ") or line.startswith("\t"):
                i += 1
                continue

            if stripped == "":
                # Look ahead to the first non-blank line.
                j = i + 1
                while j < len(lines) and lines[j].rstrip("\n").strip() == "":
                    j += 1
                if j < len(lines) and (
                    lines[j].startswith(" ") or lines[j].startswith("\t")
                ):
                    # The blank lines belong to the entry; skip past them.
                    i = j
                    continue
                # The entry has ended; the blank line is a separator, keep it.
                skip = False
                out.append(line)
                i += 1
                continue

            # Non-blank, non-indented line: the entry has ended.
            skip = False

        if stripped == f"- name: {target_name}":
            skip = True
            i += 1
            continue

        out.append(line)
        i += 1
    return out
