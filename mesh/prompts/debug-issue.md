# Prompt: Debug an issue

Refer to `mesh/skills/_common/debug/SKILL.md` for the full debugging methodology.

## Template
I have the following error/problem: {{DESCRIPTION}}

Context: {{CONTEXT}}
Relevant logs: {{LOGS}}

## Agent instructions
1. **Reproduce** — mentally trace the flow causing the error
2. **Isolate** — identify the exact component and code path involved
3. **Hypothesize** — formulate ranked hypotheses (most probable first)
4. **Verify** — propose verification steps for each hypothesis (one at a time)
5. **Fix** — suggest a minimal fix with an explanation of why it works
6. **Prevent** — propose a regression test and document the root cause
