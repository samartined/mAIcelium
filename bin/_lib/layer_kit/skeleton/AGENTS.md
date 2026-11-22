# AGENTS.md — {{name}}

{{owner}}'s skills and rules for AI agents. This repo is a source consumed by Claude Code
sessions (through the plugin in `claude/`) and by mAIcelium workspaces (as a mesh layer).

## How to work in this repo

- **One skill, one folder.** A skill is a folder with a `SKILL.md` whose `name:` equals the
  folder name. Folder names are unique across the repo.
- **Skills are self-contained.** A tool a skill needs lives inside the skill's own folder, so
  the folder can be copied anywhere and still work.
- **Rules are `.mdc` files** under `rules/_domains/<domain>/`, with `description`, and either
  `alwaysApply: true` or `globs`.
- **Third-party skills are vendored, not forked.** Copy them from an upstream tag, add a
  `VENDOR.md` with the source, tag, license and update steps, and do not edit their files.
- **Hooks are declared.** Every hook script in `claude/hooks/` has its test next to it, an entry
  in `claude/hooks/registry.json` (`origin: repo`, its `test`, the `skills` it serves, the
  `rules` it reads and the hooks it `needs`) and its events in `claude/hooks/hooks.json`.
- **Test first.** Write the test, see it fail for the expected reason, then make it pass.
- **English** in skills, rules, code, comments and commit messages.
- **Never commit credentials or secrets.**

## Do not edit

The engine files listed in `claude/engine.json` come from the mAIcelium layer kit. Change them
there and upgrade, or the next upgrade stops on the difference.
