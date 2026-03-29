# Git Workflow Skill

## When to use
When branching, committing, creating PRs, resolving conflicts, or performing
any git operation inside the mAIcelium workspace.

## Context detection
Before any git operation, determine where you are:
1. **Inside `projects/<name>/`** — use that repo's `.git` directly.
2. **Workspace root** — check if separated git mode is active
   (`bin/.git-alias.sh` exists). If so, use the alias or pass
   `--git-dir` and `--work-tree` explicitly.

Run `git rev-parse --git-dir` to confirm which repository you are operating on.

## Branching strategy
- Branch from `main` (or the project's default branch).
- Naming: `<type>/<short-description>` (e.g., `feat/add-auth`, `fix/null-pointer`).
- Types align with `commit-conventions.md`: feat, fix, docs, refactor, test, chore.
- Keep branches short-lived — merge or rebase frequently.

## Commit conventions
Follow `mesh/rules/commit-conventions.md`:
- Format: `<type>(<scope>): <description>`
- Imperative mood, lowercase, no period, max 72 chars.
- Body explains **why**, not what.
- One logical change per commit.

## Multi-project workflow
When a change spans the workspace AND a linked project:
1. Make separate, atomic commits in each repository.
2. Commit the project change first, then the workspace change.
3. Reference the project commit in the workspace commit body if relevant.

## PR workflow
1. Create feature branch: `git checkout -b <type>/<description>`
2. Commit changes following conventions.
3. Push: `git push -u origin <branch>`
4. Create PR: `gh pr create --title "<type>: <description>" --body "..."`
5. Request review, address feedback, merge.

## Conflict resolution
1. `git fetch origin` to get latest changes.
2. `git merge origin/main` (or rebase if project prefers).
3. Resolve conflicts file by file — understand both sides before choosing.
4. Run tests after resolution.
5. Commit the merge with a clear message.

## Danger zone
- **Never** force-push to `main` or `master`.
- **Never** run `git clean -fd` in the workspace root (destroys project symlinks).
- **Never** run bare `git` commands in the workspace root if separated git mode
  is active — use the `maicelium-git` alias or `/git_backup` command.
- **Never** delete branches that other agents might be using.
