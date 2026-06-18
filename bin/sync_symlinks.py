#!/usr/bin/env python3
"""Sync mesh/ symlinks into .cursor/, .agents/, .mcp.json, etc.

Replaces bin/sync_symlinks.sh. Key invariants:
- Privilege check runs FIRST, before any destructive operation.
- All symlinks are relative (portable across moves).
- Layer-managed reflections are symlinks to mesh/layers/<name>/; drift
  (real file/dir in their place) is reported, and with --fix-drift,
  identical drift is converted.
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import dataclasses
import filecmp
import json
import os
import shutil
import sys
from typing import List

from _lib.context import regenerate_claude_context, regenerate_workspace_file
from _lib.conventions import load_conventions
from _lib.platform import check_symlink_privilege, is_windows, resolve_root
from _lib.symlinks import detect_junction, find_broken_symlinks
from _lib.workspace import load_workspace_section


# ── Action plan ─────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Action:
    """Single side-effecting operation to bring the workspace into sync."""
    kind: str  # "link" | "unlink" | "mkdir" | "rmtree" | "warn" | "drift"
    src: str = ""
    dst: str = ""
    note: str = ""
    target_is_directory: bool = False


# ── Symlink helpers ─────────────────────────────────────────────────────────

def create_relative_link(src_abs, dst_abs, target_is_directory=False):
    """Create a relative symlink at dst_abs pointing to src_abs.

    Removes any pre-existing file/link at dst_abs first. The resulting link
    target is computed relative to dst_abs's parent so the link survives
    workspace moves.
    """
    rel = os.path.relpath(src_abs, os.path.dirname(dst_abs))

    try:
        if os.path.islink(dst_abs) or os.path.lexists(dst_abs):
            os.unlink(dst_abs)
    except OSError:
        if os.path.isdir(dst_abs):
            try:
                os.rmdir(dst_abs)
            except OSError:
                pass

    if is_windows():
        os.symlink(rel, dst_abs, target_is_directory=target_is_directory)
    else:
        os.symlink(rel, dst_abs)


def _is_correct_relative_symlink(dst_abs, src_abs):
    """True if dst_abs is already a symlink whose target equals the expected relative path.

    Normalizes both sides with os.path.normpath so that Windows-style
    backslash separators in the stored link target compare equal to the
    forward-slash relative path computed by os.path.relpath.
    """
    if not os.path.islink(dst_abs):
        return False
    expected = os.path.relpath(src_abs, os.path.dirname(dst_abs))
    try:
        return os.path.normpath(os.readlink(dst_abs)) == os.path.normpath(expected)
    except OSError:
        return False


# ── Drift detection ─────────────────────────────────────────────────────────

def _deep_equal(a, b):
    """True if a and b have identical file/directory contents (recursively)."""
    if os.path.isfile(a) and os.path.isfile(b):
        return filecmp.cmp(a, b, shallow=False)
    if os.path.isdir(a) and os.path.isdir(b):
        cmp = filecmp.dircmp(a, b)
        if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
            return False
        for sub in cmp.common_dirs:
            if not _deep_equal(os.path.join(a, sub), os.path.join(b, sub)):
                return False
        return True
    return False


# ── Planning helpers ────────────────────────────────────────────────────────

def _broken_unlink_actions(directory, maxdepth=None, label=""):
    """Emit unlink actions for every dangling symlink under directory."""
    actions = []
    for link in find_broken_symlinks(directory, maxdepth=maxdepth):
        actions.append(Action(kind="unlink", dst=link, note=label or "broken"))
    return actions


def _safe_link_actions(src_abs, dst_abs, fix_drift, root,
                       target_is_directory=False, src_real=None):
    """Compute the action(s) needed to ensure dst_abs is a relative symlink to src_abs.

    - If already correct: return [] (no-op).
    - If stale symlink: return [link] (overwrites).
    - If real file/dir matching content: drift detection.
        - identical + fix_drift: rmtree/unlink + link
        - identical + not fix_drift: [drift identical]
        - divergent: [drift divergent] (never overwrite)
    - If missing: [link].

    `src_real` is the path used for content comparison when src_abs goes
    through a symlink that may not yet exist (e.g., layer materialization).
    Defaults to src_abs.
    """
    actions = []
    if src_real is None:
        src_real = src_abs
    if _is_correct_relative_symlink(dst_abs, src_abs):
        return actions
    if os.path.islink(dst_abs):
        actions.append(Action(
            kind="link", src=src_abs, dst=dst_abs,
            target_is_directory=target_is_directory,
        ))
        return actions
    if os.path.exists(dst_abs):
        status = "identical" if _deep_equal(src_real, dst_abs) else "divergent"
        if fix_drift and status == "identical":
            if os.path.isdir(dst_abs) and not os.path.islink(dst_abs):
                actions.append(Action(kind="rmtree", dst=dst_abs, note="fix-drift"))
            else:
                actions.append(Action(kind="unlink", dst=dst_abs, note="fix-drift"))
            actions.append(Action(
                kind="link", src=src_abs, dst=dst_abs,
                target_is_directory=target_is_directory,
                note="fix-drift",
            ))
            return actions
        actions.append(Action(kind="drift", dst=dst_abs, note=status))
        return actions
    actions.append(Action(
        kind="link", src=src_abs, dst=dst_abs,
        target_is_directory=target_is_directory,
    ))
    return actions


# ── Layer materialization ──────────────────────────────────────────────────

def _plan_layer_materialization(root, layers, fix_drift):
    """Materialize external mesh layers under mesh/{layers,skills,rules}/.

    Equivalent of sync_symlinks.sh:71-203.
    """
    actions = []

    mesh_layers_dir = os.path.join(root, "mesh", "layers")
    mesh_skills_common = os.path.join(root, "mesh", "skills", "_common")
    mesh_skills_domain = os.path.join(root, "mesh", "skills", "_domains")
    mesh_skills_client = os.path.join(root, "mesh", "skills", "_clients")
    mesh_rules_client = os.path.join(root, "mesh", "rules", "_clients")
    mesh_rules_domain = os.path.join(root, "mesh", "rules", "_domains")

    for d in (mesh_layers_dir, mesh_skills_common, mesh_skills_domain,
              mesh_skills_client, mesh_rules_client, mesh_rules_domain):
        actions.append(Action(kind="mkdir", dst=d))

    for layer in layers:
        name = layer["name"]
        client = layer.get("client", name)
        layer_path = layer.get("path", "")
        if not layer_path or not os.path.isdir(layer_path):
            actions.append(Action(
                kind="warn", dst=layer_path,
                note=f"Layer '{name}' not found: {layer_path}",
            ))
            continue

        # mesh/layers/<name> must point at layer_path (absolute, as bash does)
        mesh_layer = os.path.join(mesh_layers_dir, name)
        layer_real = os.path.realpath(layer_path)
        if os.path.islink(mesh_layer):
            if os.path.realpath(mesh_layer) != layer_real:
                actions.append(Action(kind="unlink", dst=mesh_layer))
                actions.append(Action(
                    kind="link_abs", src=layer_path, dst=mesh_layer,
                    target_is_directory=True,
                ))
        elif os.path.isdir(mesh_layer):
            if os.path.realpath(mesh_layer) != layer_real:
                actions.append(Action(
                    kind="warn", dst=mesh_layer,
                    note=f"mesh/layers/{name} is a real directory not matching the registered path — left untouched",
                ))
        elif not os.path.exists(mesh_layer):
            actions.append(Action(
                kind="link_abs", src=layer_path, dst=mesh_layer,
                target_is_directory=True,
            ))

        # All child reflections address layer content through mesh/layers/<name>
        # so relative symlinks remain valid even if layer_path moves. The
        # planner iterates over the REAL layer_path (which may exist even
        # before the mesh_layer symlink is materialized), but the symlink
        # targets it builds use mesh_layer so they stay portable.
        skills_src_real = os.path.join(layer_path, "skills")
        skills_src_mesh = os.path.join(mesh_layer, "skills")
        if os.path.isdir(skills_src_real):
            for entry in sorted(os.listdir(skills_src_real)):
                entry_real = os.path.join(skills_src_real, entry)
                entry_mesh = os.path.join(skills_src_mesh, entry)
                if not os.path.isdir(entry_real):
                    continue
                if entry == "_common":
                    for sk in sorted(os.listdir(entry_real)):
                        sk_real = os.path.join(entry_real, sk)
                        if os.path.isdir(sk_real):
                            actions.extend(_safe_link_actions(
                                os.path.join(entry_mesh, sk),
                                os.path.join(mesh_skills_common, sk),
                                fix_drift, root, target_is_directory=True,
                                src_real=sk_real,
                            ))
                elif entry == "_domains":
                    for sk in sorted(os.listdir(entry_real)):
                        sk_real = os.path.join(entry_real, sk)
                        if os.path.isdir(sk_real):
                            actions.extend(_safe_link_actions(
                                os.path.join(entry_mesh, sk),
                                os.path.join(mesh_skills_domain, sk),
                                fix_drift, root, target_is_directory=True,
                                src_real=sk_real,
                            ))
                else:
                    client_dir = os.path.join(mesh_skills_client, client)
                    actions.append(Action(kind="mkdir", dst=client_dir))
                    actions.extend(_safe_link_actions(
                        entry_mesh,
                        os.path.join(client_dir, entry),
                        fix_drift, root, target_is_directory=True,
                        src_real=entry_real,
                    ))

        rules_src_real = os.path.join(layer_path, "rules")
        rules_src_mesh = os.path.join(mesh_layer, "rules")
        if os.path.isdir(rules_src_real):
            for entry in sorted(os.listdir(rules_src_real)):
                entry_real = os.path.join(rules_src_real, entry)
                entry_mesh = os.path.join(rules_src_mesh, entry)
                if os.path.isdir(entry_real) and entry == "_domains":
                    for domain in sorted(os.listdir(entry_real)):
                        domain_real = os.path.join(entry_real, domain)
                        domain_mesh = os.path.join(entry_mesh, domain)
                        if not os.path.isdir(domain_real):
                            continue
                        domain_dst = os.path.join(mesh_rules_domain, domain)
                        actions.append(Action(kind="mkdir", dst=domain_dst))
                        for fn in sorted(os.listdir(domain_real)):
                            if fn.endswith(".mdc"):
                                actions.extend(_safe_link_actions(
                                    os.path.join(domain_mesh, fn),
                                    os.path.join(domain_dst, fn),
                                    fix_drift, root,
                                    src_real=os.path.join(domain_real, fn),
                                ))
                elif os.path.isfile(entry_real) and entry.endswith(".mdc"):
                    client_dir = os.path.join(mesh_rules_client, client)
                    actions.append(Action(kind="mkdir", dst=client_dir))
                    actions.extend(_safe_link_actions(
                        entry_mesh,
                        os.path.join(client_dir, entry),
                        fix_drift, root,
                        src_real=entry_real,
                    ))

        actions.append(Action(
            kind="info", note=f"Layer '{name}' materialized into mesh/ (client: {client})",
        ))

    return actions


# ── Rule and skill reflection planners ──────────────────────────────────────

def _plan_rules_for(target_dir, root):
    """Emit link actions to mirror mesh rules into target_dir.

    target_dir is .cursor/rules/ or .agents/rules/. Always emits link actions
    (idempotent semantics matching bash `ln -sfn`) so that downstream sources
    that share a final filename overwrite earlier ones in registration order.
    """
    actions = []
    actions.append(Action(kind="mkdir", dst=target_dir))

    # Global mesh rules: mesh/rules/*.mdc
    rules_root = os.path.join(root, "mesh", "rules")
    if os.path.isdir(rules_root):
        for entry in sorted(os.listdir(rules_root)):
            src = os.path.join(rules_root, entry)
            if not os.path.isfile(src) or not entry.endswith(".mdc"):
                continue
            dst = os.path.join(target_dir, entry)
            actions.append(Action(kind="link", src=src, dst=dst))

    # Domain rules: mesh/rules/_domains/<domain>/*.mdc
    domains_root = os.path.join(rules_root, "_domains")
    if os.path.isdir(domains_root):
        for domain in sorted(os.listdir(domains_root)):
            domain_dir = os.path.join(domains_root, domain)
            if not os.path.isdir(domain_dir):
                continue
            for entry in sorted(os.listdir(domain_dir)):
                src = os.path.join(domain_dir, entry)
                if not os.path.isfile(src) or not entry.endswith(".mdc"):
                    continue
                dst = os.path.join(target_dir, f"domain--{domain}--{entry}")
                actions.append(Action(kind="link", src=src, dst=dst))

    # Client rules: mesh/rules/_clients/<client>/*.mdc
    clients_root = os.path.join(rules_root, "_clients")
    if os.path.isdir(clients_root):
        for client in sorted(os.listdir(clients_root)):
            client_dir = os.path.join(clients_root, client)
            if not os.path.isdir(client_dir):
                continue
            for entry in sorted(os.listdir(client_dir)):
                src = os.path.join(client_dir, entry)
                if not os.path.isfile(src) or not entry.endswith(".mdc"):
                    continue
                dst = os.path.join(target_dir, f"{client}--{entry}")
                actions.append(Action(kind="link", src=src, dst=dst))

    return actions


def _plan_skills_for(target_dir, root):
    """Emit link actions to mirror mesh skills into target_dir.

    target_dir is .cursor/skills-cursor/ or .agents/skills/. Mirrors bash
    `ln -sfn` semantics: always emits link actions so later sources (e.g.
    _common) overwrite earlier ones (e.g. native) when filenames collide.
    """
    actions = []
    actions.append(Action(kind="mkdir", dst=target_dir))

    skills_root = os.path.join(root, "mesh", "skills")
    if not os.path.isdir(skills_root):
        return actions

    # Native skills: direct children of mesh/skills/ with SKILL.md
    for entry in sorted(os.listdir(skills_root)):
        if entry in ("_common", "_domains", "_clients"):
            continue
        src = os.path.join(skills_root, entry)
        if not os.path.isdir(src):
            continue
        if not os.path.isfile(os.path.join(src, "SKILL.md")):
            continue
        dst = os.path.join(target_dir, entry)
        actions.append(Action(
            kind="link", src=src, dst=dst, target_is_directory=True,
        ))

    # _common skills: direct children
    common_root = os.path.join(skills_root, "_common")
    if os.path.isdir(common_root):
        for entry in sorted(os.listdir(common_root)):
            src = os.path.join(common_root, entry)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(target_dir, entry)
            actions.append(Action(
                kind="link", src=src, dst=dst, target_is_directory=True,
            ))

    # _domains skills: flat (folder has SKILL.md) or nested (domain--skillname)
    domains_root = os.path.join(skills_root, "_domains")
    if os.path.isdir(domains_root):
        for domain in sorted(os.listdir(domains_root)):
            domain_dir = os.path.join(domains_root, domain)
            if not os.path.isdir(domain_dir):
                continue
            if os.path.isfile(os.path.join(domain_dir, "SKILL.md")):
                dst = os.path.join(target_dir, domain)
                actions.append(Action(
                    kind="link", src=domain_dir, dst=dst,
                    target_is_directory=True,
                ))
            else:
                for entry in sorted(os.listdir(domain_dir)):
                    src = os.path.join(domain_dir, entry)
                    if not os.path.isdir(src):
                        continue
                    dst = os.path.join(target_dir, f"{domain}--{entry}")
                    actions.append(Action(
                        kind="link", src=src, dst=dst,
                        target_is_directory=True,
                    ))

    # _clients skills: <client>--<skill>
    clients_root = os.path.join(skills_root, "_clients")
    if os.path.isdir(clients_root):
        for client in sorted(os.listdir(clients_root)):
            client_dir = os.path.join(clients_root, client)
            if not os.path.isdir(client_dir):
                continue
            for entry in sorted(os.listdir(client_dir)):
                src = os.path.join(client_dir, entry)
                if not os.path.isdir(src):
                    continue
                dst = os.path.join(target_dir, f"{client}--{entry}")
                actions.append(Action(
                    kind="link", src=src, dst=dst,
                    target_is_directory=True,
                ))

    return actions


def _plan_project_imports(root, conventions):
    """Mirror per-project rules/skills/data_dirs into .cursor/ and .agents/projects/.

    Equivalent of sync_symlinks.sh:324-367. Uses absolute symlinks (matching bash
    `ln -sfn $rule $dst` where $rule is already absolute).
    """
    actions = []
    projects_dir = os.path.join(root, "projects")
    if not os.path.isdir(projects_dir):
        return actions

    data_dir_name = conventions["project_data_dir"]
    rules_subdir = conventions["project_rules_subdir"]
    skills_subdirs = conventions["project_skills_subdirs"]
    data_subdirs = conventions["project_data_subdirs"]

    cursor_rules_dir = os.path.join(root, ".cursor", "rules")
    cursor_skills_dir = os.path.join(root, ".cursor", "skills-cursor")

    for project_name in sorted(os.listdir(projects_dir)):
        link = os.path.join(projects_dir, project_name)
        if not os.path.isdir(link):
            continue
        repo_path = os.path.realpath(link)

        # Project rules
        rules_dir = os.path.join(repo_path, data_dir_name, rules_subdir)
        if os.path.isdir(rules_dir):
            for entry in sorted(os.listdir(rules_dir)):
                src = os.path.join(rules_dir, entry)
                if not os.path.isfile(src):
                    continue
                dst = os.path.join(cursor_rules_dir, f"{project_name}--{entry}")
                actions.append(Action(kind="link_abs", src=src, dst=dst))

        # Project skills (all configured skills subdirs)
        for skills_subdir in skills_subdirs:
            skills_dir = os.path.join(repo_path, data_dir_name, skills_subdir)
            if not os.path.isdir(skills_dir):
                continue
            for entry in sorted(os.listdir(skills_dir)):
                src = os.path.join(skills_dir, entry)
                if not os.path.isdir(src):
                    continue
                dst = os.path.join(cursor_skills_dir, f"{project_name}--{entry}")
                # Bash skips if link already exists, matches our intent
                if os.path.islink(dst):
                    continue
                actions.append(Action(
                    kind="link_abs", src=src, dst=dst,
                    target_is_directory=True,
                ))

        # Project data directories → .agents/projects/<project>/
        for data_sub in data_subdirs:
            full_data_dir = os.path.join(repo_path, data_dir_name, data_sub)
            if not os.path.isdir(full_data_dir):
                continue
            agents_proj_dir = os.path.join(root, ".agents", "projects", project_name)
            actions.append(Action(kind="mkdir", dst=agents_proj_dir))
            dst = os.path.join(agents_proj_dir, data_sub)
            actions.append(Action(
                kind="link_abs", src=full_data_dir, dst=dst,
                target_is_directory=True,
            ))

    return actions


def _plan_commands(root):
    """Mirror mesh/commands/*.md → .agents/workflows/."""
    actions = []
    commands_dir = os.path.join(root, "mesh", "commands")
    target_dir = os.path.join(root, ".agents", "workflows")
    actions.append(Action(kind="mkdir", dst=target_dir))
    if not os.path.isdir(commands_dir):
        return actions
    for entry in sorted(os.listdir(commands_dir)):
        if not entry.endswith(".md"):
            continue
        src = os.path.join(commands_dir, entry)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(target_dir, entry)
        actions.append(Action(kind="link", src=src, dst=dst))
    return actions


def _plan_mcp_mount(root, mcp_source):
    """Plan the mesh/mcp symlink targeting the external MCP source dir."""
    actions = []
    dst = os.path.join(root, "mesh", "mcp")

    src_path = ""
    if mcp_source:
        src_path = mcp_source.get("path", "")

    if not src_path:
        # No source registered: clear any stale symlink so generator below
        # sees no source.
        if os.path.islink(dst):
            actions.append(Action(kind="unlink", dst=dst, note="mcp-unmount"))
        return actions

    if not os.path.isdir(src_path):
        actions.append(Action(
            kind="warn", dst=src_path,
            note=f"MCP source path not found: {src_path}",
        ))
        return actions

    src_real = os.path.realpath(src_path)
    if os.path.islink(dst):
        if os.path.realpath(dst) != src_real:
            actions.append(Action(kind="unlink", dst=dst, note="mcp-remount"))
            actions.append(Action(
                kind="link_abs", src=src_path, dst=dst,
                target_is_directory=True, note="mcp-remount",
            ))
    elif os.path.exists(dst):
        actions.append(Action(
            kind="warn", dst=dst,
            note="mesh/mcp exists as a real path — left untouched",
        ))
    else:
        actions.append(Action(
            kind="link_abs", src=src_path, dst=dst,
            target_is_directory=True, note="mcp-mount",
        ))

    return actions


# ── Top-level planner ───────────────────────────────────────────────────────

def plan_actions(root, conventions, layers, mcp_source, fix_drift):
    """Compute the full action plan to bring the workspace into sync.

    Returns a list of Action dataclasses. Pure planner — no side effects
    other than read-only filesystem inspection.
    """
    actions = []

    # 1. Clean broken symlinks under .cursor/{rules,skills-cursor}
    actions.extend(_broken_unlink_actions(
        os.path.join(root, ".cursor", "rules"), label=".cursor/rules"))
    actions.extend(_broken_unlink_actions(
        os.path.join(root, ".cursor", "skills-cursor"), label=".cursor/skills-cursor"))

    # 2. Clean broken symlinks in mesh mirrors (depth-limited)
    mirror_dirs = [
        os.path.join(root, "mesh", "layers"),
        os.path.join(root, "mesh", "skills", "_common"),
        os.path.join(root, "mesh", "skills", "_domains"),
        os.path.join(root, "mesh", "skills", "_clients"),
        os.path.join(root, "mesh", "rules", "_clients"),
        os.path.join(root, "mesh", "rules", "_domains"),
    ]
    for mirror in mirror_dirs:
        if os.path.isdir(mirror):
            actions.extend(_broken_unlink_actions(
                mirror, maxdepth=3, label="mesh mirror"))

    # 3. Layer materialization + drift detection
    actions.extend(_plan_layer_materialization(root, layers, fix_drift))

    # 4. Global/domain/client rules → .cursor/rules/
    actions.extend(_plan_rules_for(os.path.join(root, ".cursor", "rules"), root))

    # 5. Clean broken in .agents/rules + mirror rules there
    agents_rules = os.path.join(root, ".agents", "rules")
    actions.append(Action(kind="mkdir", dst=agents_rules))
    actions.extend(_broken_unlink_actions(agents_rules, label=".agents/rules"))
    actions.extend(_plan_rules_for(agents_rules, root))

    # 6. Native + _common + _domains + _clients skills → .cursor/skills-cursor/
    actions.extend(_plan_skills_for(
        os.path.join(root, ".cursor", "skills-cursor"), root))

    # 7. Per-project rules/skills/data into .cursor/ and .agents/projects/
    actions.extend(_plan_project_imports(root, conventions))

    # 8. Antigravity legacy cleanup + skills mirror
    legacy_antigravity = os.path.join(root, ".antigravity")
    if os.path.exists(legacy_antigravity) or os.path.islink(legacy_antigravity):
        if os.path.islink(legacy_antigravity) or detect_junction(legacy_antigravity):
            actions.append(Action(kind="unlink", dst=legacy_antigravity, note="legacy"))
        else:
            actions.append(Action(kind="rmtree", dst=legacy_antigravity, note="legacy"))

    agents_skills = os.path.join(root, ".agents", "skills")
    actions.append(Action(kind="mkdir", dst=agents_skills))
    actions.extend(_broken_unlink_actions(agents_skills, label=".agents/skills"))
    actions.extend(_plan_skills_for(agents_skills, root))

    # 9. Commands → .agents/workflows/
    actions.extend(_plan_commands(root))

    # 10. MCP source mount
    actions.extend(_plan_mcp_mount(root, mcp_source))

    return actions


# ── Execution ───────────────────────────────────────────────────────────────

def _print_action(action):
    """Render one action for dry-run/verbose output."""
    if action.kind == "link":
        print(f"  link: {action.dst} -> {action.src} (relative)")
    elif action.kind == "link_abs":
        print(f"  link: {action.dst} -> {action.src} (absolute)")
    elif action.kind == "unlink":
        suffix = f" [{action.note}]" if action.note else ""
        print(f"  unlink: {action.dst}{suffix}")
    elif action.kind == "rmtree":
        suffix = f" [{action.note}]" if action.note else ""
        print(f"  rmtree: {action.dst}{suffix}")
    elif action.kind == "mkdir":
        print(f"  mkdir: {action.dst}")
    elif action.kind == "warn":
        print(f"  warn: {action.note}")
    elif action.kind == "drift":
        print(f"  drift [{action.note}]: {action.dst}")
    elif action.kind == "info":
        print(f"  info: {action.note}")


def execute(actions, dry_run=False):
    """Apply the action plan to the filesystem.

    When dry_run=True, prints each action without touching anything. When
    False, also prints minimal progress information. Drift actions are
    accumulated and reported at the end.
    """
    drifts = []

    for action in actions:
        if action.kind == "drift":
            drifts.append(action)
            continue

        if dry_run:
            _print_action(action)
            continue

        if action.kind == "mkdir":
            os.makedirs(action.dst, exist_ok=True)
        elif action.kind == "unlink":
            try:
                if os.path.islink(action.dst) or os.path.lexists(action.dst):
                    os.unlink(action.dst)
            except OSError:
                pass
        elif action.kind == "rmtree":
            try:
                if os.path.islink(action.dst):
                    os.unlink(action.dst)
                elif os.path.isdir(action.dst):
                    shutil.rmtree(action.dst)
                elif os.path.exists(action.dst):
                    os.remove(action.dst)
            except OSError:
                pass
        elif action.kind == "link":
            os.makedirs(os.path.dirname(action.dst), exist_ok=True)
            create_relative_link(
                action.src, action.dst,
                target_is_directory=action.target_is_directory,
            )
        elif action.kind == "link_abs":
            os.makedirs(os.path.dirname(action.dst), exist_ok=True)
            # Replace existing entry, then make absolute symlink (bash `ln -sfn`)
            try:
                if os.path.islink(action.dst) or os.path.lexists(action.dst):
                    os.unlink(action.dst)
            except OSError:
                if os.path.isdir(action.dst):
                    try:
                        os.rmdir(action.dst)
                    except OSError:
                        pass
            if is_windows():
                os.symlink(
                    action.src, action.dst,
                    target_is_directory=action.target_is_directory,
                )
            else:
                os.symlink(action.src, action.dst)
        elif action.kind == "warn":
            print(f"  Warning: {action.note}")
        elif action.kind == "info":
            print(f"  {action.note}")

    if drifts and not dry_run:
        _report_drift(drifts)


def _report_drift(drifts):
    """Emit a human-readable drift report (identical vs divergent)."""
    identical = [d for d in drifts if d.note == "identical"]
    divergent = [d for d in drifts if d.note == "divergent"]

    print("")
    print(f"Layer-managed drift detected: {len(drifts)} reflection(s) "
          "are real files/dirs instead of symlinks")
    for d in drifts:
        print(f"  - [{d.note}] {d.dst}")
    if identical:
        print("")
        print(f"  -> {len(identical)} identical reflection(s) can be "
              "auto-converted: re-run with --fix-drift")
    if divergent:
        print("")
        print(f"  -> {len(divergent)} divergent reflection(s) require "
              "manual resolution:")
        print("    1. port the delta into the matching mesh/layers/<layer>/... path,")
        print("    2. commit inside that layer repo,")
        print("    3. remove the stale reflection, then re-run this script.")


# ── MCP config generation (post-action, writes JSON files) ──────────────────

def _generate_mcp_configs(root):
    """Write .mcp.json, .cursor/mcp.json, .agents/mcp.json from mesh/mcp/*.json."""
    mcp_dir = os.path.join(root, "mesh", "mcp")
    servers = {}
    if os.path.isdir(mcp_dir):
        for fname in sorted(os.listdir(mcp_dir)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(mcp_dir, fname), encoding="utf-8") as f:
                entry = json.load(f)
            name = entry.get("name", fname.replace(".json", ""))
            servers[name] = entry.get("config", {})

    output = {"mcpServers": servers}

    # Claude Code: .mcp.json at workspace root
    with open(os.path.join(root, ".mcp.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    # Cursor: .cursor/mcp.json
    cursor_dir = os.path.join(root, ".cursor")
    os.makedirs(cursor_dir, exist_ok=True)
    with open(os.path.join(cursor_dir, "mcp.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    # Antigravity: .agents/mcp.json
    agents_dir = os.path.join(root, ".agents")
    os.makedirs(agents_dir, exist_ok=True)
    with open(os.path.join(agents_dir, "mcp.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    if servers:
        print(f"  MCP config generated ({len(servers)} server(s)): {list(servers.keys())}")
    else:
        print("  MCP config generated (no source registered)")


# ── CLAUDE.md append ────────────────────────────────────────────────────────

def _ensure_claude_md_context_reference(root):
    """Append a 'Project-specific context' section to CLAUDE.md if missing."""
    claude_md = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        return
    with open(claude_md, encoding="utf-8") as f:
        content = f.read()
    if "projects-context.md" in content:
        return
    with open(claude_md, "a", encoding="utf-8") as f:
        f.write(
            "\n## Project-specific context\n"
            "For active project rules and skills, "
            "read `.claude/projects-context.md`.\n"
        )
    print("  CLAUDE.md updated with project-context reference")


# ── WORKSPACE.md schema validation ──────────────────────────────────────────

def _has_section_marker(root, section_name):
    """True if WORKSPACE.md exists and contains the line '<section_name>:'."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.isfile(wf):
        return False
    try:
        with open(wf, encoding="utf-8") as f:
            for line in f:
                if line.strip() == f"{section_name}:":
                    return True
    except OSError:
        return False
    return False


def _workspace_file_nonempty(root):
    """True if WORKSPACE.md exists and is not empty."""
    wf = os.path.join(root, "WORKSPACE.md")
    if not os.path.isfile(wf):
        return False
    try:
        return os.path.getsize(wf) > 0
    except OSError:
        return False


# ── Entry point ─────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sync mesh/ symlinks into .cursor/, .agents/, .mcp.json, etc.",
    )
    parser.add_argument(
        "--fix-drift",
        action="store_true",
        help="Convert layer-managed real reflections into symlinks when their "
             "content matches the source layer. Divergent reflections are "
             "reported and left untouched for manual resolution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the action plan without modifying the filesystem.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Compute drift only. Exit code 0 if no drift, 1 if drift is present.",
    )
    args = parser.parse_args(argv)

    root = resolve_root()

    # 1. Privilege check FIRST — abort cleanly before any destructive op.
    if not check_symlink_privilege():
        sys.stderr.write(
            "Cannot create symbolic links. "
            "Enable Developer Mode on Windows.\n"
        )
        return 2

    # 2. Load state
    conventions = load_conventions(root)
    layers = load_workspace_section(root, "mesh_layers")
    mcp_source = load_workspace_section(root, "mcp_source")

    # 3. Schema-validate WORKSPACE.md: empty section + marker present = degraded.
    degraded = False
    if _workspace_file_nonempty(root):
        if _has_section_marker(root, "mesh_layers") and not layers:
            degraded = True

    # 4. Plan
    actions = plan_actions(root, conventions, layers, mcp_source, args.fix_drift)

    # 5. Check-only short-circuit
    if args.check_only:
        drifts = [a for a in actions if a.kind == "drift"]
        if drifts:
            for a in drifts:
                sys.stderr.write(f"drift: {a.dst} [{a.note}]\n")
            return 1
        return 0

    # 6. Execute
    print("Syncing symlinks...")
    execute(actions, dry_run=args.dry_run)

    if args.dry_run:
        print("Dry run complete; no changes applied.")
        return 0

    # 7. Post-actions (file generators, not part of the action plan)
    _generate_mcp_configs(root)
    regenerate_claude_context(root)
    _ensure_claude_md_context_reference(root)
    regenerate_workspace_file(root)
    print("  Workspace file regenerated")
    print("Symlinks synced.")

    if degraded:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
