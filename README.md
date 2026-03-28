# mAIcelium

A centralized, multi-IDE workspace that connects AI coding agents to shared knowledge — like a fungal network feeding nutrients to every organism in the forest.

<p align="center">
  <img src="docs/assets/mAIcelium-architecture.png" alt="mAIcelium architecture overview" width="720" />
</p>

## The problem

When you work with multiple AI-powered IDEs (Cursor, Claude Code, Antigravity), each one maintains its own rules, skills, and context in isolation. You end up duplicating configurations, losing consistency, and manually keeping things in sync.

## The solution

mAIcelium provides a single workspace directory where:

- **One source of truth** (`ai/`) holds all rules, skills, prompts, and commands.
- **Symlinks** distribute that knowledge to each IDE in the format it expects.
- **Projects plug in and out** without copying files — just symlinks to your real repos.
- **Scripts automate everything** — no manual symlink management.

```mermaid
graph LR
    AI["ai/"] -->|symlinks| Cursor[".cursor/"]
    AI -->|"CLAUDE.md"| Claude[".claude/"]
    AI -->|symlinks| Antigravity[".antigravity/"]
    Projects["projects/"] -->|symlinks| Repos["Your repos"]
```

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/your-user/mAIcelium.git
cd mAIcelium

# 2. Initialize the workspace
bin/init.sh

# 3. Register your repos (edit with your actual paths)
cp repos/_registry.yaml.example repos/_registry.yaml
# edit repos/_registry.yaml

# 4. Plug in a project
bin/add_project.sh my-api ~/dev/my-api

# 5. Open this directory in your IDEs and start working
```

## Workspace structure

```
mAIcelium/
├── ai/                        # Single source of truth for AI agents
│   ├── rules/                 # Global rules (coding standards, security, commits)
│   ├── skills/                # Reusable capabilities
│   │   ├── _common/           # Universal skills (code-review, planning, etc.)
│   │   ├── _clients/          # Client-specific skills
│   │   └── _domains/          # Tech stack skills (React, Python, DevOps)
│   ├── commands/              # Agent command definitions
│   └── prompts/               # Reusable prompt templates
├── bin/                       # Automation scripts
│   ├── init.sh                # Initialize the workspace
│   ├── add_project.sh         # Plug in a project
│   ├── remove_project.sh      # Unplug a project
│   └── sync_symlinks.sh       # Rebuild all symlinks
├── projects/                  # Symlinks to active repos
├── repos/                     # Repository registry
├── .cursor/                   # Auto-generated Cursor config (symlinks)
├── .claude/                   # Claude Code config + auto-generated context
├── .antigravity/              # Auto-generated Antigravity config (symlinks)
├── CLAUDE.md                  # Entry point for Claude Code agents
├── AGENTS.md                  # Agent permissions and coordination rules
└── WORKSPACE.md               # Dynamic state — active projects list
```

## IDE responsibilities

| IDE | Role | How it connects |
|-----|------|----------------|
| **Cursor** | Code implementation | Symlinks in `.cursor/rules/` and `.cursor/skills-cursor/` |
| **Claude Code** | Planning, architecture, analysis | Reads `CLAUDE.md` → navigates to `ai/` directly |
| **Antigravity** | Refactoring, review, scoped tasks | Symlinks in `.antigravity/` |

## Documentation

- **[Architecture](docs/architecture.md)** — How the system works, with diagrams
- **[Getting Started](docs/getting-started.md)** — Step-by-step walkthrough with examples
- **[Reference](docs/reference.md)** — Scripts, commands, rules, and skills reference

## Key commands

| Command | Description |
|---------|-------------|
| `bin/init.sh` | Initialize a fresh workspace |
| `bin/add_project.sh <name> <path>` | Plug in a project |
| `bin/remove_project.sh <name>` | Unplug a project (original repo untouched) |
| `bin/sync_symlinks.sh` | Rebuild all symlinks after changes |

## License

MIT

---

<sub>Cursor, Claude, and Antigravity are trademarks of their respective owners. This project is not affiliated with or endorsed by Anysphere, Anthropic, or Google.</sub>
