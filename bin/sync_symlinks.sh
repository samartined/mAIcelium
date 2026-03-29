#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bin/_lib.sh"
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

# ── Recreate mAIcelium global skills → .cursor/skills-cursor/ ────────────────
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
    # Nested domain: each child folder is a skill; link parent as single entry
    ln -sfn "../../mesh/skills/_domains/$domain" "$ROOT/.cursor/skills-cursor/$domain"
  fi
done

# ── Recreate project-specific rules and skills ───────────────────────────────
for project_link in "$ROOT"/projects/*/; do
  [ -d "$project_link" ] || continue
  project_name=$(basename "$project_link")
  repo_path=$(realpath "$project_link")

  # Project rules
  if [ -d "$repo_path/.cursor/rules" ]; then
    for rule in "$repo_path"/.cursor/rules/*; do
      [ -f "$rule" ] || continue
      rulename=$(basename "$rule")
      ln -sfn "$rule" "$ROOT/.cursor/rules/${project_name}--${rulename}"
    done
  fi

  # Project skills (.cursor/skills/ and .cursor/skills-cursor/)
  for skills_dir in "$repo_path/.cursor/skills" "$repo_path/.cursor/skills-cursor"; do
    [ -d "$skills_dir" ] || continue
    for skill_dir in "$skills_dir"/*/; do
      [ -d "$skill_dir" ] || continue
      skillname=$(basename "$skill_dir")
      [ -L "$ROOT/.cursor/skills-cursor/${project_name}--${skillname}" ] && continue
      ln -sfn "$skill_dir" "$ROOT/.cursor/skills-cursor/${project_name}--${skillname}"
    done
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
      ln -sfn "../../../mesh/skills/_domains/$domain/$skillname" "$ROOT/.agents/skills/${domain}--${skillname}"
    done
  fi
done

# Map commands to workflows
for cmd_file in "$ROOT"/mesh/commands/*.md; do
  [ -f "$cmd_file" ] || continue
  name=$(basename "$cmd_file")
  ln -sfn "../../mesh/commands/$name" "$ROOT/.agents/workflows/$name"
done

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
