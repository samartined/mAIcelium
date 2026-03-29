# Reference

Quick-reference for all scripts, agent commands, rules, skills, and configuration files in the mAIcelium workspace.

---

## Scripts

All scripts live in `bin/` and are executed from the workspace root.

| Script | Purpose | Usage |
|--------|---------|-------|
| `init.sh` | Initialize a fresh workspace — creates directories, symlinks, and config files | `bin/init.sh` |
| `add_project.sh` | Plug in a project by creating symlinks and importing its rules/skills | `bin/add_project.sh <name> <path>` |
| `remove_project.sh` | Unplug a project — removes symlinks, original repo untouched | `bin/remove_project.sh <name>` |
| `sync_symlinks.sh` | Rebuild all symlinks — cleans broken ones, recreates from `mesh/` and active projects | `bin/sync_symlinks.sh` |
| `separate_git.sh` | Move `.git` outside workspace to avoid IDE conflicts with linked projects | `bin/separate_git.sh` |
| `hooks/guard-bash.sh` | Security hook that blocks destructive shell commands before they execute | — |
| `hooks/guard-write.sh` | Security hook that protects sensitive and auto-generated files from being modified | — |
| `_lib.sh` | Shared functions (sourced by other scripts, not run directly) | — |

### `add_project.sh` details

```bash
bin/add_project.sh my-api ~/dev/my-api
```

- Validates project name (alphanumeric, hyphens, underscores only)
- Warns if the path is not in `repos/_registry.yaml`
- Fails if the project name already exists (use `remove_project.sh` first)
- Imports project rules as `.cursor/rules/<name>--<rule>`
- Imports project skills as `.cursor/skills-cursor/<name>--<skill>`
- Checks both `.cursor/skills/` and `.cursor/skills-cursor/` in the project repo

### `remove_project.sh` details

```bash
bin/remove_project.sh my-api
```

- Shows active projects if no name is provided
- Removes all `<name>--*` symlinks from `.cursor/rules/` and `.cursor/skills-cursor/`
- Removes the `projects/<name>` symlink only — **never the target directory**
- Updates `WORKSPACE.md` and `.claude/projects-context.md`

### `sync_symlinks.sh` details

```bash
bin/sync_symlinks.sh
```

Run this after:
- Adding new files to `mesh/rules/` or `mesh/skills/`
- Moving the workspace to a different path
- Recovering from broken symlinks
- Any manual changes to the `mesh/` directory

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

All rules live in `mesh/rules/`. They are prescriptive — agents must follow them.

| Rule | File | Purpose |
|------|------|---------|
| **Global** | `global.md` | Agent identity, mandatory workflow (read WORKSPACE.md first), IDE responsibilities, commit types, safety rules, language policy |
| **Coding Standards** | `coding-standards.md` | Strict TypeScript, composition over inheritance, pure functions, max 20 lines, descriptive names, DRY, early returns |
| **Commit Conventions** | `commit-conventions.md` | Conventional Commits format: `<type>(<scope>): <description>`. Types: feat, fix, docs, refactor, test, chore |
| **Security Checklist** | `security-checklist.md` | Pre-commit checks (no credentials), auth best practices, input/output validation, infrastructure, Docker security |
| **Architecture Principles** | `architecture-principles.md` | Clean Architecture, SRP, domain-organized structure, RESTful APIs, versioned migrations, stateless design |
| **Workspace Conventions** | `workspace-conventions.md` | `mesh/` as source of truth, naming conventions (kebab-case), command output format, file placement reference |

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

Skills live in `mesh/skills/` organized by category. Each skill has a `SKILL.md` with instructions.

### Universal skills (`_common/`)

| Skill | Directory | Purpose |
|-------|-----------|---------|
| **Code Review** | `_common/code-review/` | Analyze architecture, error handling, security, readability. Classify findings as blocker / suggestion / nit. |
| **Planning** | `_common/planning/` | Decompose features into atomic tasks, estimate complexity (S/M/L), identify dependencies and risks. |
| **Workspace Guide** | `_common/workspace-guide/` | Auto-orientation for agents: always write to `mesh/`, naming conventions, command output format, symlink architecture. |
| **Git Workflow** | `_common/git-workflow/` | Git operations, branching strategy, PR workflow. |
| **Testing** | `_common/testing/` | Test strategy, coverage, edge cases. |
| **Documentation** | `_common/documentation/` | Writing and maintaining docs. |

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
| `WORKSPACE.md` | Lists active projects with paths and timestamps | Auto-generated by `add/remove_project.sh` |
| `.claude/settings.json` | Claude Code permissions (allowed bash commands, PreToolUse hooks for write/bash protection) | Generated by `init.sh`, can be edited |
| `.claude/projects-context.md` | Lists rules and skills of active projects for Claude Code | Auto-generated by scripts |
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
| `WORKSPACE.md` | Dynamic state, regenerated by scripts |
| `.claude/projects-context.md` | Auto-generated |
| `/repos/_registry.yaml` | Contains user-specific local paths |
| `bin/.git-alias.sh` | Generated by `separate_git.sh`, contains local paths |
| `.env` | Environment variables with secrets |

---

## IDE connection summary

| IDE | Config location | Connection mechanism | Project-specific |
|-----|----------------|---------------------|-----------------|
| **Cursor** | `.cursor/rules/`, `.cursor/skills-cursor/` | Per-file symlinks from `mesh/` | `<project>--<rule>` prefixed symlinks |
| **Claude Code** | `CLAUDE.md`, `.claude/` | Direct file access, reads `mesh/` paths from `CLAUDE.md` | `.claude/projects-context.md` (auto-generated) |
| **Antigravity** | `.antigravity/rules`, `.antigravity/skills` | Directory-level symlinks to `mesh/` | Via directory symlinks (sees everything in `mesh/`) |
