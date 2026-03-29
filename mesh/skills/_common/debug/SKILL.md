# Debug Skill

## When to use
When investigating bug reports, unexpected behavior, test failures,
or production incidents. Complements the `debug-issue` prompt template.

## Step 1: Reproduce
Define the exact conditions that trigger the bug:
- **Input**: what data or action causes it.
- **Expected**: what should happen.
- **Actual**: what happens instead.

If you cannot reproduce, gather more context before proceeding.
Check logs, error messages, and environment differences.

## Step 2: Isolate
Narrow down where the bug lives:
- **Binary search** the call stack — add logging at midpoints to determine
  which half contains the divergence.
- Identify the **exact function and line** where actual behavior departs
  from expected behavior.
- Simplify the reproduction case to the minimum inputs that trigger the bug.

## Step 3: Hypothesize
Generate ranked hypotheses (most probable first):
1. State the hypothesis clearly.
2. Define what evidence would confirm or refute it.
3. Check the simplest explanations first: typos, wrong variable,
   off-by-one, stale cache, environment mismatch.

## Step 4: Verify
Test **one hypothesis at a time**:
- Change one thing, observe the result.
- Do not shotgun-fix multiple things simultaneously.
- If a hypothesis is refuted, revert the change and move to the next.

## Step 5: Fix
Apply the **minimal fix** that addresses the root cause:
- Use `fix(<scope>):` commit type (ref: `commit-conventions.md`).
- Explain **why** the fix works in the commit body.
- Do not refactor unrelated code in the same commit.

## Step 6: Prevent
- Write a test that would have caught this bug (regression test).
- Consider if the root cause could affect other code paths.
- If the finding is significant, propose documenting it in techcorpus.

## Multi-project context
- Verify which project the bug is in: check if you are looking at the
  correct repo via `projects/<name>/` (symlink) vs workspace root.
- Bugs in workspace scripts (`bin/`, `mesh/`) affect all projects.
- Bugs in project code are isolated to that project's repo.

## Anti-patterns
- Do not guess and check randomly — follow the steps in order.
- Do not fix symptoms without understanding the root cause.
- Do not make multiple changes at once — isolate variables.
- Do not ignore intermittent bugs — they usually indicate race conditions
  or state leaks.
