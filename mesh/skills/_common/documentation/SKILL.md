---
name: documentation
description: >-
  When writing or updating READMEs, API documentation, changelogs, inline documentation, or propagating knowledge to techcorpus.
---
# Documentation Skill

## When to use
When writing or updating READMEs, API documentation, changelogs,
inline documentation, or propagating knowledge to techcorpus.

## README structure
A good README answers: what is this, how do I use it, how do I contribute?

1. **Title** — project name.
2. **Description** — one paragraph explaining purpose and value.
3. **Prerequisites** — required tools, versions, accounts.
4. **Installation** — step-by-step setup commands.
5. **Usage** — common operations with examples.
6. **Configuration** — environment variables, config files.
7. **Development** — how to run tests, lint, build.
8. **License** — if applicable.

Keep it scannable. Use code blocks for commands. Avoid walls of text.

## Changelog conventions
Follow [Keep a Changelog](https://keepachangelog.com/) format.

| Commit type | Changelog category |
|-------------|-------------------|
| feat        | Added             |
| fix         | Fixed             |
| docs        | _(usually skip)_  |
| refactor    | Changed           |
| chore       | _(usually skip)_  |

Group entries under a version header with a date: `## [1.2.0] - 2026-03-29`.

## API documentation
- For REST APIs: document with OpenAPI/Swagger
  (ref: `architecture-principles.md`).
- For libraries: document public interfaces, parameters, return types.
- For CLI tools: document all commands, flags, and examples.
- Include request/response examples for non-obvious endpoints.

## Inline documentation
Code should be self-documenting (ref: `coding-standards.md`).
Add comments only for:
- **Why** a decision was made (not what the code does).
- Workarounds with links to the issue they address.
- Non-obvious side effects or constraints.
- Public API contracts (parameters, return values, exceptions).

## Knowledge propagation to techcorpus
When solving a non-trivial problem or learning something reusable:
1. Check if it belongs in techcorpus (the knowledge vault).
2. Use the `obsidian-markdown` skill for proper formatting.
3. Place it in the appropriate area (backend, devops, tools, etc.).
4. Link related notes with wikilinks.

## Language
AI configuration files (rules, skills, references) must be in English
(ref: `ai-files-language.md`). User-facing documentation follows the
project's own language conventions.
