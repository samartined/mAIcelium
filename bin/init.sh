#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "🍄 Initializing mAIcelium at: $ROOT"

mkdir -p "$ROOT"/mesh/skills/{_common/{code-review,git-workflow,testing,planning,documentation},_clients,_domains/{frontend-react,backend-python,devops}}
mkdir -p "$ROOT"/mesh/{rules,prompts,commands}
mkdir -p "$ROOT"/{.cursor/{rules,skills-cursor},.claude/commands,.agents,projects,repos,bin}
touch "$ROOT/projects/.gitkeep" "$ROOT/mesh/skills/_clients/.gitkeep"

echo "  → Creating Cursor symlinks..."
for rule in "$ROOT"/mesh/rules/*.mdc; do
  [ -f "$rule" ] || continue
  name=$(basename "$rule")
  ln -sfn "../../mesh/rules/$name" "$ROOT/.cursor/rules/$name"
done
for skill_dir in "$ROOT"/mesh/skills/_common/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  ln -sfn "../../mesh/skills/_common/$name" "$ROOT/.cursor/skills-cursor/$name"
done
for skill_dir in "$ROOT"/mesh/skills/_domains/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  ln -sfn "../../mesh/skills/_domains/$name" "$ROOT/.cursor/skills-cursor/$name"
done
echo "  ✔ Cursor symlinks created"

echo "  → Creating Antigravity (.agents/) symlinks..."
mkdir -p "$ROOT/.agents/rules" "$ROOT/.agents/skills" "$ROOT/.agents/workflows"
for rule in "$ROOT"/mesh/rules/*.mdc; do
  [ -f "$rule" ] || continue
  name=$(basename "$rule")
  ln -sfn "../../mesh/rules/$name" "$ROOT/.agents/rules/$name"
done
for skill_dir in "$ROOT"/mesh/skills/_common/*/; do
  [ -d "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  ln -sfn "../../mesh/skills/_common/$name" "$ROOT/.agents/skills/$name"
done
for cmd_file in "$ROOT"/mesh/commands/*.md; do
  [ -f "$cmd_file" ] || continue
  name=$(basename "$cmd_file")
  ln -sfn "../../mesh/commands/$name" "$ROOT/.agents/workflows/$name"
done
echo "  ✔ Antigravity (.agents/) symlinks created"

if [ ! -f "$ROOT/.claude/settings.json" ]; then
  cat > "$ROOT/.claude/settings.json" << 'EOF'
{
  "permissions": {
    "allow": [
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(find:*)",
      "Bash(realpath:*)",
      "Bash(ln:*)",
      "Bash(rm:*)",
      "Bash(mkdir:*)",
      "Bash(bash:bin/*)",
      "Bash(python3:mesh/commands/scripts/*)"
    ]
  }
}
EOF
  echo "  ✔ .claude/settings.json created"
else
  echo "  ✔ .claude/settings.json already exists (kept)"
fi

if [ ! -f "$ROOT/WORKSPACE.md" ]; then
  cat > "$ROOT/WORKSPACE.md" << WSEOF
# Active workspace

projects: []

created: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
WSEOF
  echo "  ✔ WORKSPACE.md created"
else
  echo "  ✔ WORKSPACE.md already exists (kept)"
fi

if [ ! -f "$ROOT/repos/_registry.yaml" ] && [ -f "$ROOT/repos/_registry.yaml.example" ]; then
  cp "$ROOT/repos/_registry.yaml.example" "$ROOT/repos/_registry.yaml"
  echo "  ✔ repos/_registry.yaml created from template"
fi

echo "  → Creating smug symlink..."
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/smug"
ln -sfn "$ROOT/.smug.yml" "${XDG_CONFIG_HOME:-$HOME/.config}/smug/mAIcelium.yml"
echo "  ✔ smug symlink created"

chmod +x "$ROOT"/bin/*.sh
echo "  ✔ Script permissions set"

echo ""
echo "✅ mAIcelium initialized successfully."
echo "   Next step: open this directory in your IDEs"
