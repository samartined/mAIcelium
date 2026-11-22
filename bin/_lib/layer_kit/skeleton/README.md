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
- Skills that must stay out of every session go in `claude/global.json` under `exclude`.
- Works on Linux and macOS.

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

## Engine updates

`claude/` comes from the mAIcelium layer kit. `mai skills-repo update <folder>` replaces the
engine files only, and stops if any of them was edited here. Hooks marked `"origin": "repo"`
in the registry are yours and are never touched.
