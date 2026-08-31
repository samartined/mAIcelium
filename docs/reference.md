# Reference

Quick-reference for all scripts, agent commands, rules, skills, and configuration files in the mAIcelium workspace.

---

## The `mai` CLI

`mai` is the unified shell front-end that dispatches to the same `bin/` and
`mesh/commands/scripts/` scripts you would otherwise run with `python3 bin/…`.

### Installation

```bash
# Recommended — editable install; puts mai on PATH as a console-script entry point
pip install -e .

# Zero-install alternative — run the committed shims from the checkout directly
./mai          # POSIX (already chmod +x)
mai.cmd        # Windows
```

**Editable-only limitation:** a non-editable wheel (`pip install .` without `-e`) copies
`maicelium_cli.py` to site-packages and severs its link to the `bin/` directory next to it.
A detached install requires `MAICELIUM_ROOT` to be set explicitly, or `--root` to be passed.
For normal workspace use, always use `pip install -e .`.

### Usage

```
mai [--root <path>] [--version | -V] [--help | -h]
mai <verb> [args...]
```

Global flags must appear **before** the verb. Everything after the verb is forwarded
verbatim to the target script — `mai sync --check-only`, `mai sync --help`, and
`mai set-flag my-api key val` all reach the real script unmodified.

### Global flags

| Flag | Description |
|------|-------------|
| `--root <path>` | Override workspace root (validated: must be an existing directory) |
| `--version`, `-V` | Print version and exit 0 |
| `--help`, `-h` | Print help listing all verbs and exit 0 |

### Verb table

| Canonical verb | Aliases | Target script | Summary |
|----------------|---------|---------------|---------|
| `init` | — | `bin/init.py` | Scaffold a new mAIcelium workspace |
| `add` | `add-project`, `add_project` | `bin/add_project.py` | Add a project symlink (exact-name bin/ writer, not fuzzy) |
| `remove` | `rm`, `remove-project`, `remove_project` | `bin/remove_project.py` | Remove a project symlink |
| `sync` | `sync-symlinks`, `sync_symlinks` | `bin/sync_symlinks.py` | Sync workspace symlinks (check/fix drift) |
| `separate-git` | `git-separate`, `separate_git` | `bin/separate_git.py` | Separate a project's git history |
| `add-mcp` | `add-mcp-source`, `add_mcp_source` | `bin/add_mcp_source.py` | Mount an external MCP definitions directory |
| `remove-mcp` | `remove-mcp-source`, `remove_mcp_source` | `bin/remove_mcp_source.py` | Unmount the current MCP source |
| `add-layer` | `add-mesh-layer`, `add_mesh_layer` | `bin/add_mesh_layer.py` | Add a mesh layer |
| `remove-layer` | `remove-mesh-layer`, `remove_mesh_layer` | `bin/remove_mesh_layer.py` | Remove a mesh layer |
| `set-flag` | `set-project-flag`, `set_project_flag` | `bin/set_project_flag.py` | Set a project flag |
| `list` | `ls`, `list-projects`, `list_projects` | `mesh/commands/scripts/list_projects.py` | List all linked projects |
| `health` | `project-health`, `project_health` | `mesh/commands/scripts/project_health.py` | Run health checks across all linked projects |

**Note on `add` / `remove`:** these target the deterministic `bin/` writers, not the
`mesh/commands/scripts/` fuzzy-matching variants used by IDE slash commands.
The shell CLI is always exact; fuzzy matching stays a slash-command affordance.

### Workspace root resolution

`mai` resolves the workspace root in this order (first match wins):

1. `--root <path>` on the command line (validated: must be an existing directory; exits 2 if not).
2. `MAICELIUM_ROOT` environment variable, if set and non-empty (passed through verbatim — not existence-validated, unlike `--root`).
3. Upward walk from the current working directory, looking for a directory that contains both `bin/_bootstrap.py` and `mesh/`. The nearest matching ancestor wins (first-match-wins is deterministic on nested workspaces).
4. The directory of `maicelium_cli.py` itself — works for editable installs where the module lives next to `bin/`.

The resolved root is exported to every child script as `MAICELIUM_ROOT`, so all downstream resolvers agree.

### Exit-code policy

| Code | Meaning |
|------|---------|
| `0` | Success (also: `mai`, `mai --help`, `mai --version`) |
| `1` | Child script reported an error (e.g. `remove` with no args prints Usage and exits 1) |
| `2` | Router-level error (unknown verb, unknown global flag, bad/missing `--root`) **or** child exit 2 passed through verbatim |
| `130` | Interrupted (Ctrl-C / SIGINT) |

**Important — exit 2 is overloaded.** The router uses 2 for its own usage errors, but child
scripts can also legitimately return 2 (e.g. `sync` returns 2 on certain error conditions and 3
on others; `init` returns 2 when symlink privilege is unavailable). Do not use `exit 2` as a
reliable signal that the invocation was malformed — inspect stderr for the router's own error
messages if you need to distinguish the cases.

**`mai health`** exits 0 when the workspace is healthy and non-zero (2) when a project symlink
is broken. Broken-symlink details are always printed in the report text regardless of exit code.

---

## Scripts

All scripts live in `bin/` and are executed from the workspace root.

| Script | Purpose | Usage |
|--------|---------|-------|
| `init.py` | Initialize a fresh workspace — creates directories, symlinks, and config files | `python3 bin/init.py` |
| `add_project.py` | Plug in a project by creating symlinks and importing its rules/skills | `python3 bin/add_project.py <path> <name>` |
| `remove_project.py` | Unplug a project — removes symlinks, original repo untouched | `python3 bin/remove_project.py <name>` |
| `sync_symlinks.py` | Rebuild all symlinks — cleans broken ones, recreates from `mesh/`, mounted layers, and active projects | `python3 bin/sync_symlinks.py` |
| `separate_git.py` | Move `.git` outside workspace to avoid IDE conflicts with linked projects | `python3 bin/separate_git.py` |
| `hooks/guard_bash.py` | Best-effort PreToolUse guard that blocks common literal destructive shell commands (defense-in-depth, not a security barrier; bypassable via shell expansion; fails open by design) | — |
| `hooks/guard_write.py` | Security hook that protects sensitive and auto-generated files from being modified | — |
| `_lib.py` | Shared functions (imported by other scripts, not run directly) | — |

### `add_project.py` details

```bash
# path first (canonical) — or name first; both work
python3 bin/add_project.py ~/dev/my-api my-api
```

- **Either order**: the positional that is an existing directory (resolved relative to
  the current directory, so a bare folder name with no slash also counts) is taken as
  the path, the other as the name. Pass `--path <path>` / `--name <name>` to be explicit.
- **Ambiguity is a hard error**: if both positionals are existing directories, the
  command refuses to guess and asks you to use `--path`/`--name`.
  (`add_mesh_layer.py` accepts its `<path>`/`<name>` the same either-order way.)
- Validates project name (alphanumeric, hyphens, underscores only)
- Warns if the path is not in `repos/_registry.yaml`
- Fails if the project name already exists (use `remove_project.py` first)
- Imports project rules as `.cursor/rules/<name>--<rule>`
- Imports project skills as `.cursor/skills-cursor/<name>--<skill>`
- Checks both `.cursor/skills/` and `.cursor/skills-cursor/` in the project repo

### `remove_project.py` details

```bash
python3 bin/remove_project.py my-api
```

- Shows active projects if no name is provided
- Removes all `<name>--*` symlinks from `.cursor/rules/` and `.cursor/skills-cursor/`
- Removes the `projects/<name>` symlink only — **never the target directory**
- Updates `WORKSPACE.md` and `.claude/projects-context.md`

### `sync_symlinks.py` details

```bash
python3 bin/sync_symlinks.py
```

Run this after:
- Adding new files to `mesh/rules/`, `mesh/skills/`, or `mesh/layers/`
- Adding or changing MCP definitions in `mesh/mcp/`
- Moving the workspace to a different path
- Recovering from broken symlinks
- Any manual changes to the `mesh/` directory

The script rebuilds `.cursor/`, `.agents/`, MCP configs, `.claude/projects-context.md`, and `mAIcelium.code-workspace`. It also resolves mounted layer content and removes legacy `.antigravity/` directories.

---

## Agent commands

These commands can be used in IDEs that support agent commands (e.g., Claude Code's `/command` syntax). Commands with fuzzy matching use Python scripts in `mesh/commands/scripts/`.

| Command | Description | Fuzzy | Defined in |
|---------|-------------|-------|------------|
| `/add_project <name>` | Fuzzy-match a project from the registry and plug it in | ✔ | `mesh/commands/add_project.md` |
| `/remove_project <name>` | Fuzzy-match a linked project and unplug it | ✔ | `mesh/commands/remove_project.md` |
| `/list_projects` | Show all currently linked projects | — | `mesh/commands/list_projects.md` |
| `/workspace_status` | Show active projects, skills, rules, and symlink status | — | `mesh/commands/workspace_status.md` |
| `/project_health` | Diagnostic health check across all linked projects | — | `mesh/commands/project_health.md` |
| `/git_backup [message]` | Stage, commit, and push workspace changes | — | `mesh/commands/git_backup.md` |

For Claude Code, these commands are wired through `.claude/commands/*.yaml` files that point to the definitions in `mesh/commands/`.

### Fuzzy matching

The `/add_project` and `/remove_project` commands support fuzzy matching via Python scripts (`mesh/commands/scripts/`). The matching resolves approximate names in this order:

1. Exact match (case-insensitive, ignoring hyphens/underscores)
2. Substring containment (if unambiguous)
3. Bigram similarity scoring (Jaccard index ≥ 0.4)

When ambiguous, the command returns candidates prefixed with ❓ and the agent asks the user to clarify.

---

## Rules

Rules are consumed from `mesh/rules/`. Depending on the workspace setup, some rule paths can be direct files and others can be symlink-mounted from `mesh/layers/*`.

| Rule | File | Purpose |
|------|------|---------|
| **Global** | `global.mdc` | Agent identity, mandatory workflow (read WORKSPACE.md first), IDE responsibilities, commit types, safety rules, language policy |
| **mAIcelium Identity** | `maicelium-identity.mdc` | Framework identity, architecture overview, scripts, commands, and safety hooks reference |
| **AI Files Language** | `ai-files-language.mdc` | All AI configuration files (rules, skills, references) must be written in English |
| **Commit Conventions** | `commit-conventions.mdc` | Conventional Commits format: `<type>(<scope>): <description>`. Types: feat, fix, docs, refactor, test, chore |
| **Workspace Conventions** | `workspace-conventions.mdc` | `mesh/` as source of truth, naming conventions (kebab-case), command output format, file placement reference |
| **Coding Standards** | `_domains/software/coding-standards.mdc` | Strict TypeScript, composition over inheritance, pure functions, max 20 lines, descriptive names, DRY, early returns |
| **Security Checklist** | `_domains/software/security-checklist.mdc` | Pre-commit checks (no credentials), auth best practices, input/output validation, infrastructure, Docker security |
| **Architecture Principles** | `_domains/software/architecture-principles.mdc` | Clean Architecture, SRP, domain-organized structure, RESTful APIs, versioned migrations, stateless design |

### Commit conventions

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | No functional change |
| `test` | Add or fix tests |
| `chore` | Maintenance, dependencies |

**Format:** `<type>(<scope>): <description>`

**Examples:**
```
feat(auth): add Google OAuth login
fix(api): handle timeout on /users endpoint
docs(readme): update setup instructions
```

---

## Skills

Skills are consumed from `mesh/skills/` organized by category. Depending on the setup, `_common` and `_domains` paths may be direct directories or symlink-mounted from `mesh/layers/*`. Each skill has a `SKILL.md` with instructions.

### Universal skills (`_common/`)

| Skill | Directory | Purpose |
|-------|-----------|---------|
| **Code Review** | `_common/code-review/` | Analyze architecture, error handling, security, readability. Classify findings as blocker / suggestion / nit. |
| **Planning** | `_common/planning/` | Decompose features into atomic tasks, estimate complexity (S/M/L), identify dependencies and risks. |
| **Workspace Guide** | `_common/workspace-guide/` | Auto-orientation for agents: always write to `mesh/`, naming conventions, command output format, symlink architecture. |
| **Git Workflow** | `_common/git-workflow/` | Git operations, branching strategy, PR workflow. |
| **Testing** | `_common/testing/` | Test strategy, coverage, edge cases. |
| **Documentation** | `_common/documentation/` | Writing and maintaining docs. |
| **Debug** | `_common/debug/` | Systematic debugging: reproduce, isolate, hypothesize, fix, verify. |
| **Refactoring** | `_common/refactoring/` | Safe refactoring workflows: identify scope, plan changes, validate behavior preservation. |
| **Security Review** | `_common/security-review/` | Security-focused code review: secrets, auth, injection, dependencies. |
| **Cursor Workspace Migration** | `_domains/cursor/cursor-workspace-migration/` | Migrate Cursor chat history and workspace data between machines. |

### Tech stack skills (`_domains/`)

| Skill | Directory | Purpose |
|-------|-----------|---------|
| **Frontend React** | `_domains/frontend-react/` | React patterns, component architecture, state management. |
| **Backend Python** | `_domains/backend-python/` | Python best practices, FastAPI, Django patterns. |
| **DevOps** | `_domains/devops/` | CI/CD, Docker, Kubernetes, cloud infrastructure. |

### Client skills (`_clients/`)

Reserved for client-specific knowledge and workflows. Add directories as needed.

---

## Prompt templates

Reusable prompt templates live in `mesh/prompts/`. They use `{{PLACEHOLDER}}` syntax for variable substitution.

| Template | File | Use case |
|----------|------|----------|
| **Debug an issue** | `debug-issue.md` | Systematic debugging: reproduce flow, identify components, rank hypotheses, propose fix |
| **Review a PR** | `review-pr.md` | Code review using the code-review skill, classify findings, provide examples |
| **Plan a feature** | `plan-feature.md` | Feature breakdown, dependency ordering, effort estimation, risk identification |

---

## Configuration files

| File | Purpose | Managed by |
|------|---------|------------|
| `CLAUDE.md` | Entry point for Claude Code agents — points to `mesh/`, `WORKSPACE.md`, and `.claude/projects-context.md` | Manual (version-controlled) |
| `AGENTS.md` | Agent permissions, coordination rules, safety constraints | Manual (version-controlled) |
| `WORKSPACE.md` | Lists active projects with paths and timestamps | Auto-generated by `add/remove_project.py` |
| `.claude/settings.json` | Claude Code permissions (allowed bash commands, PreToolUse hooks for write/bash protection) | Version-controlled; initial version generated by `init.py` |
| `.claude/commands/*.yaml` | Claude Code slash command bindings | Version-controlled |
| `.claude/projects-context.md` | Inlines rules and skills of active projects for Claude Code | Auto-generated by scripts |
| `mAIcelium.code-workspace` | Multi-root VS Code/Cursor workspace with each project as a root | Auto-generated by scripts |
| `.smug.yml` | Tmux session layout for the workspace (optional) | Manual |
| `repos/_registry.yaml` | YAML registry of all available repos with paths and tech stacks | Manual (`.gitignored`) |

---

## Repository registry format

`repos/_registry.yaml` organizes repos by category:

```yaml
clients:
  client-name:
    description: "Client description"
    repos:
      repo-name:
        path: ~/dev/path/to/repo
        tech: [language, framework, database]

personal:
  project-name:
    path: ~/dev/path
    tech: [language]

development:
  tool-name:
    path: ~/dev/tools
    tech: [bash]
```

---

## Gitignored files

These files are excluded from version control because they contain machine-specific or dynamic content:

| Pattern | Reason |
|---------|--------|
| `/projects/*` | Symlinks to user-specific local paths |
| `/mesh/layers/*` | Standalone layer repos mounted into `mesh/` via symlinks |
| `WORKSPACE.md` | Dynamic state, regenerated by scripts |
| `.cursor/` | Auto-generated IDE symlinks (recreated by `sync_symlinks.py`) |
| `.agents/` | Auto-generated Antigravity config (recreated by `sync_symlinks.py`) |
| `.mcp.json` | Auto-generated MCP config |
| `*.code-workspace` | Auto-generated multi-root workspace file |
| `.claude/projects-context.md` | Auto-generated project context for Claude Code |
| `.claude/settings.local.json` | Local overrides for Claude Code settings |
| `/repos/_registry.yaml` | Contains user-specific local paths |
| `bin/.git-alias.sh` | Generated by `separate_git.py`, contains local paths |
| `.env` | Environment variables with secrets |
| `docs/assets/backup/` | Image backup files |

---

## IDE connection summary

| IDE | Config location | Connection mechanism | Project-specific |
|-----|----------------|---------------------|-----------------|
| **Cursor** | `.cursor/rules/`, `.cursor/skills-cursor/` | Per-file symlinks from `mesh/` | `<project>--<rule>` prefixed symlinks |
| **Claude Code** | `CLAUDE.md`, `.claude/` | Direct file access, reads `mesh/` paths from `CLAUDE.md` | `.claude/projects-context.md` (auto-generated) |
| **Antigravity** | `.agents/rules/`, `.agents/skills/`, `.agents/workflows/` | Per-file symlinks from `mesh/`, flattened skills, commands as workflows | `.agents/projects/<name>/` with project data symlinks |
