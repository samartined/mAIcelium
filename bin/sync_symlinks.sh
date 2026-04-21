#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
_load_conventions "$ROOT"
MESH_LAYERS="$(_load_mesh_layers "$ROOT")"
MCP_SOURCE="$(_load_mcp_source "$ROOT")"

# ── Optional flags ───────────────────────────────────────────────────────────
# --fix-drift : when a mesh/ reflection exists as a real file/dir instead of a
#               symlink to a layer, replace it with a symlink IF its content is
#               identical to the layer's version. Divergent reflections are
#               always reported and never overwritten.
FIX_DRIFT=0
for arg in "$@"; do
  case "$arg" in
    --fix-drift) FIX_DRIFT=1 ;;
    --help|-h)
      cat <<USAGE
Usage: $(basename "$0") [--fix-drift]

  --fix-drift   Convert layer-managed real reflections into symlinks when their
                content matches the source layer. Divergent reflections are
                reported and left untouched for manual resolution.
USAGE
      exit 0
      ;;
  esac
done
export MAICELIUM_FIX_DRIFT="$FIX_DRIFT"

echo "🔄 Syncing symlinks..."

# ── Clean broken symlinks ────────────────────────────────────────────────────
BROKEN=$(find -L "$ROOT/.cursor/rules" -type l 2>/dev/null)
if [ -n "$BROKEN" ]; then
  echo "⚠️  Removing broken symlinks in .cursor/rules/:"
  echo "$BROKEN" | while read -r link; do
    echo "  - $(basename "$link")"
    rm "$link"
  done
fi

BROKEN=$(find -L "$ROOT/.cursor/skills-cursor" -type l 2>/dev/null)
if [ -n "$BROKEN" ]; then
  echo "⚠️  Removing broken symlinks in .cursor/skills-cursor/:"
  echo "$BROKEN" | while read -r link; do
    echo "  - $(basename "$link")"
    rm "$link"
  done
fi

# ── Clean broken symlinks in mesh/ internal mirrors ──────────────────────────
for MIRROR_DIR in \
  "$ROOT/mesh/layers" \
  "$ROOT/mesh/skills/_common" \
  "$ROOT/mesh/skills/_domains" \
  "$ROOT/mesh/skills/_clients" \
  "$ROOT/mesh/rules/_clients" \
  "$ROOT/mesh/rules/_domains"; do
  [ -d "$MIRROR_DIR" ] || continue
  BROKEN=$(find -L "$MIRROR_DIR" -maxdepth 3 -type l 2>/dev/null || true)
  if [ -n "$BROKEN" ]; then
    echo "⚠️  Removing broken symlinks in ${MIRROR_DIR#"$ROOT"/}:"
    echo "$BROKEN" | while read -r link; do
      echo "  - ${link#"$ROOT"/}"
      rm "$link"
    done
  fi
done

# ── Materialize mesh layers → mesh/ internal dirs ────────────────────────────
# For every layer registered in WORKSPACE.md, expose its content through the
# mesh/ tree so it appears uniformly in the file explorer:
#   - mesh/layers/<name>                → external layer path (symlink if external)
#   - mesh/skills/_common/<skill>       → ../../layers/<name>/skills/_common/<skill>
#   - mesh/skills/_domains/<skill>      → ../../layers/<name>/skills/_domains/<skill>
#   - mesh/skills/_clients/<client>/<s> → ../../../layers/<name>/skills/<s>
#   - mesh/rules/_domains/<domain>/<r>  → ../../../layers/<name>/rules/_domains/<d>/<r>
#   - mesh/rules/_clients/<client>/<r>  → ../../../layers/<name>/rules/<r>
# Downstream _clients/*, _common/*, _domains/* loops then produce .cursor/ and
# .agents/ symlinks transparently — no layer-specific duplication needed.
python3 - "$ROOT" "$MESH_LAYERS" <<'PYEOF'
import filecmp, json, os, shutil, sys

root, layers_json = sys.argv[1], sys.argv[2]
layers = json.loads(layers_json)
fix_drift = os.environ.get("MAICELIUM_FIX_DRIFT") == "1"

mesh_layers_dir    = os.path.join(root, "mesh", "layers")
mesh_skills_common = os.path.join(root, "mesh", "skills", "_common")
mesh_skills_domain = os.path.join(root, "mesh", "skills", "_domains")
mesh_skills_client = os.path.join(root, "mesh", "skills", "_clients")
mesh_rules_client  = os.path.join(root, "mesh", "rules", "_clients")
mesh_rules_domain  = os.path.join(root, "mesh", "rules", "_domains")

for d in (mesh_layers_dir, mesh_skills_common, mesh_skills_domain,
          mesh_skills_client, mesh_rules_client, mesh_rules_domain):
    os.makedirs(d, exist_ok=True)

drift_detected = []  # list of tuples: (dst, status) where status in {"identical","divergent"}

def deep_equal(a, b):
    """Return True if a and b have identical file/directory contents (recursively)."""
    if os.path.isfile(a) and os.path.isfile(b):
        return filecmp.cmp(a, b, shallow=False)
    if os.path.isdir(a) and os.path.isdir(b):
        cmp = filecmp.dircmp(a, b)
        if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
            return False
        for sub in cmp.common_dirs:
            if not deep_equal(os.path.join(a, sub), os.path.join(b, sub)):
                return False
        return True
    return False

def safe_link(src_abs, dst):
    """Create relative symlink dst → src_abs.
    - Replace stale symlinks.
    - Real files/dirs are reported as drift; with --fix-drift (env
      MAICELIUM_FIX_DRIFT=1), identical reflections are replaced by a symlink.
      Divergent reflections are never overwritten — they require manual resolution."""
    rel = os.path.relpath(src_abs, os.path.dirname(dst))
    if os.path.islink(dst):
        if os.readlink(dst) == rel:
            return
        os.remove(dst)
        os.symlink(rel, dst)
        return
    if os.path.exists(dst):
        status = "identical" if deep_equal(src_abs, dst) else "divergent"
        if fix_drift and status == "identical":
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            else:
                os.remove(dst)
            os.symlink(rel, dst)
            print(f"  🔧 fix-drift: replaced real reflection with symlink → {os.path.relpath(dst, root)}")
            return
        drift_detected.append((dst, status))
        return
    os.symlink(rel, dst)

for layer in layers:
    name = layer['name']
    client = layer.get('client', name)
    layer_path = layer.get('path', '')
    if not layer_path or not os.path.isdir(layer_path):
        print(f"  ⚠️  Layer '{name}' not found: {layer_path}")
        continue

    # 1. Ensure mesh/layers/<name> is accessible
    mesh_layer = os.path.join(mesh_layers_dir, name)
    layer_real = os.path.realpath(layer_path)
    if os.path.islink(mesh_layer):
        if os.path.realpath(mesh_layer) != layer_real:
            os.remove(mesh_layer)
            os.symlink(layer_path, mesh_layer)
    elif os.path.isdir(mesh_layer):
        if os.path.realpath(mesh_layer) != layer_real:
            print(f"  ⚠️  mesh/layers/{name} is a real directory not matching "
                  f"the registered path — left untouched")
    elif not os.path.exists(mesh_layer):
        os.symlink(layer_path, mesh_layer)

    # All child paths are addressed through mesh/layers/<name> so that
    # the relative symlinks we produce stay valid across moves.
    skills_src = os.path.join(mesh_layer, "skills")
    if os.path.isdir(skills_src):
        for entry in sorted(os.listdir(skills_src)):
            entry_abs = os.path.join(skills_src, entry)
            if not os.path.isdir(entry_abs):
                continue
            if entry == "_common":
                for sk in sorted(os.listdir(entry_abs)):
                    sk_abs = os.path.join(entry_abs, sk)
                    if os.path.isdir(sk_abs):
                        safe_link(sk_abs, os.path.join(mesh_skills_common, sk))
            elif entry == "_domains":
                for sk in sorted(os.listdir(entry_abs)):
                    sk_abs = os.path.join(entry_abs, sk)
                    if os.path.isdir(sk_abs):
                        safe_link(sk_abs, os.path.join(mesh_skills_domain, sk))
            else:
                client_dir = os.path.join(mesh_skills_client, client)
                os.makedirs(client_dir, exist_ok=True)
                safe_link(entry_abs, os.path.join(client_dir, entry))

    rules_src = os.path.join(mesh_layer, "rules")
    if os.path.isdir(rules_src):
        for entry in sorted(os.listdir(rules_src)):
            entry_abs = os.path.join(rules_src, entry)
            if os.path.isdir(entry_abs) and entry == "_domains":
                for domain in sorted(os.listdir(entry_abs)):
                    domain_abs = os.path.join(entry_abs, domain)
                    if not os.path.isdir(domain_abs):
                        continue
                    domain_dst = os.path.join(mesh_rules_domain, domain)
                    os.makedirs(domain_dst, exist_ok=True)
                    for fn in sorted(os.listdir(domain_abs)):
                        if fn.endswith(".mdc"):
                            safe_link(os.path.join(domain_abs, fn),
                                      os.path.join(domain_dst, fn))
            elif os.path.isfile(entry_abs) and entry.endswith(".mdc"):
                client_dir = os.path.join(mesh_rules_client, client)
                os.makedirs(client_dir, exist_ok=True)
                safe_link(entry_abs, os.path.join(client_dir, entry))

    print(f"  ✔ Layer '{name}' materialized into mesh/ (client: {client})")

if drift_detected:
    print("")
    print(f"⚠️  Layer-managed drift detected: {len(drift_detected)} reflection(s) are real files/dirs instead of symlinks")
    identical = [d for d in drift_detected if d[1] == "identical"]
    divergent = [d for d in drift_detected if d[1] == "divergent"]
    for dst, status in drift_detected:
        rel_dst = os.path.relpath(dst, root)
        print(f"  - [{status}] {rel_dst}")
    if not fix_drift and identical:
        print("")
        print(f"  → {len(identical)} identical reflection(s) can be auto-converted: re-run with --fix-drift")
    if divergent:
        print("")
        print(f"  → {len(divergent)} divergent reflection(s) require manual resolution:")
        print(f"    1. port the delta into the matching mesh/layers/<layer>/... path,")
        print(f"    2. commit inside that layer repo,")
        print(f"    3. remove the stale reflection, then re-run this script.")
PYEOF

# ── Recreate mAIcelium global rules → .cursor/rules/ ────────────────────────
for rule in "$ROOT"/mesh/rules/*.mdc; do
  [ -f "$rule" ] || continue
  name=$(basename "$rule")
  ln -sfn "../../mesh/rules/$name" "$ROOT/.cursor/rules/$name"
done

# ── Recreate mAIcelium domain rules → .cursor/rules/ ───────────────────────
for domain_dir in "$ROOT"/mesh/rules/_domains/*/; do
  [ -d "$domain_dir" ] || continue
  domain=$(basename "$domain_dir")
  for rule in "$domain_dir"*.mdc; do
    [ -f "$rule" ] || continue
    name=$(basename "$rule")
    ln -sfn "../../mesh/rules/_domains/$domain/$name" "$ROOT/.cursor/rules/domain--${domain}--${name}"
  done
done

# _clients rules → .cursor/rules/<client>--<name>  (legacy: mesh/_clients/ fallback)
for client_dir in "$ROOT"/mesh/rules/_clients/*/; do
  [ -d "$client_dir" ] || continue
  client=$(basename "$client_dir")
  for rule in "$client_dir"*.mdc; do
    [ -f "$rule" ] || continue
    name=$(basename "$rule")
    ln -sfn "../../mesh/rules/_clients/$client/$name" "$ROOT/.cursor/rules/${client}--${name}"
  done
done

# Layer rules are materialized into mesh/rules/_clients/<client>/ and
# mesh/rules/_domains/<domain>/ by the materialization block above; downstream
# _clients/ and _domains/ loops then produce .cursor/rules/ symlinks.

# ── Recreate mAIcelium rules → .agents/rules/ (Antigravity) ─────────────────
mkdir -p "$ROOT/.agents/rules"

BROKEN=$(find -L "$ROOT/.agents/rules" -type l 2>/dev/null)
if [ -n "$BROKEN" ]; then
  echo "⚠️  Removing broken symlinks in .agents/rules/:"
  echo "$BROKEN" | while read -r link; do
    echo "  - $(basename "$link")"
    rm "$link"
  done
fi

for rule in "$ROOT"/mesh/rules/*.mdc; do
  [ -f "$rule" ] || continue
  name=$(basename "$rule")
  ln -sfn "../../mesh/rules/$name" "$ROOT/.agents/rules/$name"
done

for domain_dir in "$ROOT"/mesh/rules/_domains/*/; do
  [ -d "$domain_dir" ] || continue
  domain=$(basename "$domain_dir")
  for rule in "$domain_dir"*.mdc; do
    [ -f "$rule" ] || continue
    name=$(basename "$rule")
    ln -sfn "../../mesh/rules/_domains/$domain/$name" "$ROOT/.agents/rules/domain--${domain}--${name}"
  done
done

# _clients rules → .agents/rules/<client>--<name>  (legacy: mesh/_clients/ fallback)
for client_dir in "$ROOT"/mesh/rules/_clients/*/; do
  [ -d "$client_dir" ] || continue
  client=$(basename "$client_dir")
  for rule in "$client_dir"*.mdc; do
    [ -f "$rule" ] || continue
    name=$(basename "$rule")
    ln -sfn "../../mesh/rules/_clients/$client/$name" "$ROOT/.agents/rules/${client}--${name}"
  done
done
# (Layer rules already linked above in the shared Python block)

# ── Recreate mAIcelium global skills → .cursor/skills-cursor/ ────────────────
# Native skills: direct children of mesh/skills/ (e.g. mesh/skills/workspace-guide/)
# — these are mAIcelium-intrinsic, tracked in the mAIcelium repo itself, and do
# not live in any layer. Skipped: the special _common/_domains/_clients buckets.
for skill_dir in "$ROOT"/mesh/skills/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  case "$name" in _common|_domains|_clients) continue ;; esac
  [ -f "$skill_dir/SKILL.md" ] || continue
  ln -sfn "../../mesh/skills/$name" "$ROOT/.cursor/skills-cursor/$name"
done

# _common skills: direct children (e.g., _common/planning/)
for skill_dir in "$ROOT"/mesh/skills/_common/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  ln -sfn "../../mesh/skills/_common/$name" "$ROOT/.cursor/skills-cursor/$name"
done

# _domains skills: support both flat (e.g., _domains/devops/) and nested
# (e.g., _domains/obsidian/json-canvas/). A domain folder is a skill if it
# contains SKILL.md directly; otherwise its children are individual skills.
for domain_dir in "$ROOT"/mesh/skills/_domains/*/; do
  [ -d "$domain_dir" ] || continue
  domain=$(basename "$domain_dir")
  if [ -f "$domain_dir/SKILL.md" ]; then
    # Flat domain: the folder itself is the skill
    ln -sfn "../../mesh/skills/_domains/$domain" "$ROOT/.cursor/skills-cursor/$domain"
  else
    # Nested domain: link each child skill individually (domain--skillname)
    for skill_dir in "$domain_dir"*/; do
      [ -d "$skill_dir" ] || continue
      skillname=$(basename "$skill_dir")
      ln -sfn "../../mesh/skills/_domains/$domain/$skillname" "$ROOT/.cursor/skills-cursor/${domain}--${skillname}"
    done
  fi
done

# _clients skills → .cursor/skills-cursor/<client>--<skill>
for client_dir in "$ROOT"/mesh/skills/_clients/*/; do
  [ -d "$client_dir" ] || continue
  client=$(basename "$client_dir")
  for skill_dir in "$client_dir"*/; do
    [ -d "$skill_dir" ] || continue
    skillname=$(basename "$skill_dir")
    ln -sfn "../../mesh/skills/_clients/$client/$skillname" "$ROOT/.cursor/skills-cursor/${client}--${skillname}"
  done
done

# ── Recreate project-specific rules and skills ───────────────────────────────
for project_link in "$ROOT"/projects/*/; do
  [ -d "$project_link" ] || continue
  project_name=$(basename "$project_link")
  repo_path=$(realpath "$project_link")

  # Project rules
  if [ -d "$repo_path/$MESH_PROJECT_DATA_DIR/$MESH_PROJECT_RULES_SUBDIR" ]; then
    for rule in "$repo_path/$MESH_PROJECT_DATA_DIR/$MESH_PROJECT_RULES_SUBDIR"/*; do
      [ -f "$rule" ] || continue
      rulename=$(basename "$rule")
      ln -sfn "$rule" "$ROOT/.cursor/rules/${project_name}--${rulename}"
    done
  fi

  # Project skills (all configured skills subdirs)
  for skills_subdir in $MESH_PROJECT_SKILLS_SUBDIRS; do
    skills_dir="$repo_path/$MESH_PROJECT_DATA_DIR/$skills_subdir"
    [ -d "$skills_dir" ] || continue
    for skill_dir in "$skills_dir"/*/; do
      [ -d "$skill_dir" ] || continue
      skillname=$(basename "$skill_dir")
      [ -L "$ROOT/.cursor/skills-cursor/${project_name}--${skillname}" ] && continue
      ln -sfn "$skill_dir" "$ROOT/.cursor/skills-cursor/${project_name}--${skillname}"
    done
  done

  # Project data directories — symlinked into .agents/projects/<project>/ for Antigravity access
  for data_dir in $MESH_PROJECT_DATA_SUBDIRS; do
    full_data_dir="$repo_path/$MESH_PROJECT_DATA_DIR/$data_dir"
    [ -d "$full_data_dir" ] || continue
    mkdir -p "$ROOT/.agents/projects/$project_name"
    ln -sfn "$full_data_dir" "$ROOT/.agents/projects/$project_name/$data_dir"
  done
done

# ── Antigravity (.agents/) ───────────────────────────────────────────────────
rm -rf "$ROOT/.antigravity"  # Remove legacy configuration
mkdir -p "$ROOT/.agents/skills"
mkdir -p "$ROOT/.agents/workflows"

# Clean broken symlinks in .agents/skills/
BROKEN=$(find -L "$ROOT/.agents/skills" -type l 2>/dev/null)
if [ -n "$BROKEN" ]; then
  echo "⚠️  Removing broken symlinks in .agents/skills/:"
  echo "$BROKEN" | while read -r link; do
    echo "  - $(basename "$link")"
    rm "$link"
  done
fi

# Native skills (mesh/skills/<name>/) → .agents/skills/
for skill_dir in "$ROOT"/mesh/skills/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  case "$name" in _common|_domains|_clients) continue ;; esac
  [ -f "$skill_dir/SKILL.md" ] || continue
  ln -sfn "../../mesh/skills/$name" "$ROOT/.agents/skills/$name"
done

# Flatten _common skills → .agents/skills/
for skill_dir in "$ROOT"/mesh/skills/_common/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  ln -sfn "../../mesh/skills/_common/$name" "$ROOT/.agents/skills/$name"
done

# Flatten _domains skills
for domain_dir in "$ROOT"/mesh/skills/_domains/*/; do
  [ -d "$domain_dir" ] || continue
  domain=$(basename "$domain_dir")
  if [ -f "$domain_dir/SKILL.md" ]; then
    ln -sfn "../../mesh/skills/_domains/$domain" "$ROOT/.agents/skills/$domain"
  else
    for skill_dir in "$domain_dir"*/; do
      [ -d "$skill_dir" ] || continue
      skillname=$(basename "$skill_dir")
      ln -sfn "../../mesh/skills/_domains/$domain/$skillname" "$ROOT/.agents/skills/${domain}--${skillname}"
    done
  fi
done

# Flatten _clients skills → .agents/skills/<client>--<skill>  (legacy: mesh/_clients/ fallback)
for client_dir in "$ROOT"/mesh/skills/_clients/*/; do
  [ -d "$client_dir" ] || continue
  client=$(basename "$client_dir")
  for skill_dir in "$client_dir"*/; do
    [ -d "$skill_dir" ] || continue
    skillname=$(basename "$skill_dir")
    ln -sfn "../../../mesh/skills/_clients/$client/$skillname" "$ROOT/.agents/skills/${client}--${skillname}"
  done
done

# Layer skills are materialized into mesh/skills/_clients/<client>/,
# mesh/skills/_common/ and mesh/skills/_domains/ by the materialization block
# above; downstream _clients/, _common/ and _domains/ loops then produce
# .cursor/skills-cursor/ and .agents/skills/ symlinks.

# Map commands to workflows
for cmd_file in "$ROOT"/mesh/commands/*.md; do
  [ -f "$cmd_file" ] || continue
  name=$(basename "$cmd_file")
  ln -sfn "../../mesh/commands/$name" "$ROOT/.agents/workflows/$name"
done

# ── MCP source mount ───────────────────────────────────────────────────────────
# mesh/mcp is a symlink to the external MCP definitions directory registered in
# WORKSPACE.md under `mcp_source:`. If no source is registered the symlink is
# removed so stale mounts do not leak into generated configs.
python3 - "$ROOT" "$MCP_SOURCE" <<'MCPMOUNT'
import json, os, sys

root = sys.argv[1]
src_json = sys.argv[2]
dst = os.path.join(root, "mesh", "mcp")

src_path = ""
if src_json:
    try:
        src_path = json.loads(src_json).get("path", "")
    except json.JSONDecodeError:
        src_path = ""

if not src_path:
    # Unmount: clear any stale symlink so the generator below sees no source
    if os.path.islink(dst):
        os.remove(dst)
    sys.exit(0)

if not os.path.isdir(src_path):
    print(f"  \u26a0\ufe0f  MCP source path not found: {src_path}")
    sys.exit(0)

src_real = os.path.realpath(src_path)
if os.path.islink(dst):
    if os.path.realpath(dst) != src_real:
        os.remove(dst)
        os.symlink(src_path, dst)
        print(f"  \u2714 MCP source remounted \u2192 {src_path}")
elif os.path.exists(dst):
    print(f"  \u26a0\ufe0f  mesh/mcp exists as a real path \u2014 left untouched")
    sys.exit(0)
else:
    os.symlink(src_path, dst)
    print(f"  \u2714 MCP source mounted \u2192 {src_path}")
MCPMOUNT

# ── MCP configurations ─────────────────────────────────────────────────────────
# Generate IDE-specific MCP config from mesh/mcp/*.json canonical definitions.
# Cursor and Claude Code share the same mcpServers format.
# Antigravity (.agents/mcp.json) uses the same format — verify against their docs if needed.
python3 -c '
import json, os, sys

root = sys.argv[1]
mcp_dir = os.path.join(root, "mesh", "mcp")

servers = {}
if os.path.isdir(mcp_dir):
    for fname in sorted(os.listdir(mcp_dir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(mcp_dir, fname)) as f:
            entry = json.load(f)
        name = entry.get("name", fname.replace(".json", ""))
        servers[name] = entry.get("config", {})

output = {"mcpServers": servers}

# Claude Code: .mcp.json at workspace root (project-scoped, no secrets)
with open(os.path.join(root, ".mcp.json"), "w") as f:
    json.dump(output, f, indent=2)
    f.write("\n")

# Cursor: .cursor/mcp.json (workspace-level, complements global ~/.cursor/mcp.json)
cursor_dir = os.path.join(root, ".cursor")
os.makedirs(cursor_dir, exist_ok=True)
with open(os.path.join(cursor_dir, "mcp.json"), "w") as f:
    json.dump(output, f, indent=2)
    f.write("\n")

# Antigravity: .agents/mcp.json (same format — adjust if their spec differs)
agents_dir = os.path.join(root, ".agents")
os.makedirs(agents_dir, exist_ok=True)
with open(os.path.join(agents_dir, "mcp.json"), "w") as f:
    json.dump(output, f, indent=2)
    f.write("\n")

if servers:
    print(f"  ✔ MCP config generated ({len(servers)} server(s)): {list(servers.keys())}")
else:
    print(f"  ✔ MCP config generated (no source registered)")
' "$ROOT"

# ── Claude Code: regenerate project context ──────────────────────────────────
_regenerate_claude_context "$ROOT"

# ── Claude Code: ensure CLAUDE.md references project context (idempotent) ────
if [ -f "$ROOT/CLAUDE.md" ] && ! grep -q "projects-context.md" "$ROOT/CLAUDE.md"; then
  printf '\n## Project-specific context\nFor active project rules and skills, read `.claude/projects-context.md`.\n' >> "$ROOT/CLAUDE.md"
  echo "  ✔ CLAUDE.md updated with project-context reference"
fi

# ── Multi-root workspace file ────────────────────────────────────────────────
_regenerate_workspace_file "$ROOT"
echo "  ✔ Workspace file regenerated"

echo "✅ Symlinks synced."
echo ""
echo "Cursor rules:"
ls -la "$ROOT/.cursor/rules/"
echo ""
echo "Cursor skills:"
ls -la "$ROOT/.cursor/skills-cursor/"
