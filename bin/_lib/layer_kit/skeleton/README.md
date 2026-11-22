# {{name}}

{{owner}}'s skills and rules for AI agents. This repo is a **source**: Claude Code reads it
directly in any session, and a mAIcelium workspace can mount it as a mesh layer.

## Layout

```
{{name}}/
├── rules/_domains/<domain>/*.mdc       rules, grouped by technical domain
├── skills/_common/<skill>/SKILL.md     skills for any kind of work
├── skills/_domains/<domain>/<skill>/   skills scoped to one domain
└── claude/                             the engine that brings all of this to Claude Code
```

## Use it in every Claude Code session

On each machine, once:

```sh
git clone <this repo's URL> <folder>
python3 <folder>/claude/doctor.py --fix
```

From then on every new session sees these skills and runs their hooks, wherever it
starts. Each session start keeps the skill links in step with the repo, and in the
background it pulls `main` (only when the copy is clean) and re-checks the Claude Code
behaviour the setup relies on after each Claude Code update. It speaks only when you
have to do something.

- `python3 claude/doctor.py` reports the state; `--fix` repairs it; `--uninstall` removes
  everything it added.
- Works on Linux and macOS.

## Settings

| File | What it holds |
|------|---------------|
| `claude/global.json` | `exclude`: skills never linked into every session. `state_dir`: the state folder's name, when it must differ from the plugin name. `private_words`: words `mai kit share` refuses to copy out of this repo (clients, employers, organizations) |
| `claude/hard-rules.md` | Rules for every session on your machines; `doctor.py --fix` imports it from `~/.claude/CLAUDE.md` |
| `claude/hooks/registry.json` | Each hook: its script, its test, the skills it serves, the rules it reads and the hooks it needs |

## Use it in mAIcelium

```sh
mai add-layer <folder> {{name}}
```

Both ways can be used at once: inside the workspace every skill still loads once.

## Add a skill

1. Create `skills/_common/<name>/SKILL.md` (or under `skills/_domains/<domain>/`) with
   `name: <name>` and a `description` in its frontmatter. The name must match the folder.
2. If the skill needs a hook, put the script and its test in `claude/hooks/`, declare it in
   `claude/hooks/registry.json` and wire it in `claude/hooks/hooks.json`.
3. Run the tests in `claude/tests/` and `claude/hooks/`.

## Give some of it to someone

From a mAIcelium workspace that mounts this repo as a layer:

```sh
mai kit share <folder> --owner "<their name>" --from <this repo> --only <domain>
```

It copies the skills and rules you name, with their hooks, and refuses to copy anything
that identifies you or this repo.

## Engine updates

`claude/` comes from the mAIcelium layer kit. `mai kit update <folder>` replaces the
engine files only, and stops if any of them was edited here. Hooks marked `"origin": "repo"`
in the registry are yours and are never touched.
