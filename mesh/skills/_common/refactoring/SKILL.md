---
name: refactoring
description: >-
  When improving code structure without changing behavior: reducing complexity, eliminating duplication, preparing for a new feature, or addressing review feedback. This is the primary skill for Antigravity's role (refactoring, review, scoped tasks).
---
# Refactoring Skill

## When to use
When improving code structure without changing behavior: reducing complexity,
eliminating duplication, preparing for a new feature, or addressing review feedback.
This is the primary skill for Antigravity's role (refactoring, review, scoped tasks).

## Pre-refactoring checklist
Before touching any code:
- [ ] Tests exist and pass for the code being refactored.
- [ ] Git working tree is clean (commit or stash pending changes).
- [ ] You know which project you are in (`projects/<name>/`).
- [ ] Scope is clear — confirm with the user if the refactoring is large.

If tests do not exist, write them first (ref: `testing` skill).

## Step 1: Identify the smell
Name it explicitly. Common smells:
- **Long method** — function exceeds 20 lines (ref: `coding-standards.md`).
- **God class** — class with too many responsibilities.
- **Feature envy** — method uses another class's data more than its own.
- **Duplicate code** — same logic in multiple places.
- **Shotgun surgery** — one change requires edits in many files.
- **Primitive obsession** — using primitives instead of domain types.

## Step 2: Plan the transformation
Define:
- **Current state** — what the code does now and why it smells.
- **Target state** — what the code should look like after.
- **Steps** — each step should be a single, commit-sized change.

## Step 3: Execute
- One transformation per commit. Use `refactor(<scope>):` commit type.
- Run tests after each step. If tests break, **revert the step** — do not proceed.
- Keep each commit small enough to review in isolation.

## Common transformations
| Smell              | Transformation                          |
|--------------------|-----------------------------------------|
| Long method        | Extract function                        |
| God class          | Extract class / split by responsibility |
| Duplicate code     | Extract shared utility                  |
| Deep nesting       | Early returns, guard clauses            |
| Primitive obsession| Introduce value object / type alias     |
| Feature envy       | Move method to the class it envies      |

## Multi-agent safety
If another agent may be working on the same codebase:
- Scope refactoring to a single file or module per commit.
- Avoid renaming public APIs without coordination.
- Conflicts are resolved at the git level (ref: `AGENTS.md`).

## Verify
After all steps are complete:
- Run the full test suite — no regressions.
- Review the combined diff — confirm no behavioral change.
- Ensure the target state matches what was planned.
