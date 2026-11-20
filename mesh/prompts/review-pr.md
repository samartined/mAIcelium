# Prompt: Review a PR

## Template
Review the following PR/diff: {{PR_REF}}

## Agent instructions
1. Use the structured-code-review skill (mesh/skills/_common/structured-code-review/SKILL.md)
2. Analyze each modified file
3. Evaluate against coding-standards and security-checklist rules
4. Generate actionable feedback with code examples
5. Classify findings with the skill's severity scale: important / pre-existing / nit
