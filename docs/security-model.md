# Security model

How mAIcelium's PreToolUse hooks decide what an agent may write, and what they
deliberately leave to other layers.

The two hooks are `bin/hooks/guard_write.py` (Write, Edit, MultiEdit,
NotebookEdit) and `bin/hooks/guard_bash.py` (Bash). Both delegate file decisions
to one shared, standard-library-only module, `bin/hooks/_policy.py`.

## Threat model

**Defends against:** an agent that makes a mistake, or that content in a repo it
reads has manipulated, acting with the user's own permissions.

**Does not defend against:** the user themselves, or anyone with access to the
machine. Neither hook is a sandbox.

**Protects:**
- The agent only writes where the user has deliberately mounted something:
  - the workspace;
  - the repos linked under `projects/`, `mesh/layers/` and `mesh/mcp`;
  - the harness folders listed under [Write roots](#write-roots).
- Inside those, it does not touch secrets, `.git` internals, lockfiles, agent
  settings or the guards themselves.

**Deliberately not protected:** Bash is not a boundary. A program the agent runs
can write anywhere the user can. `guard_bash` is a speed-bump against obvious
mistakes, plus a check on the files a command visibly writes. See
[Residual risks](#residual-risks).

**Rule of gold:** judge the destination file, not the tool that writes it. The
same `.env` gets the same decision from `Write` and from `cat <<EOF > .env`.

## Hook stacking

Claude Code runs every hook registered for an event, and one deny is enough:
- the global hooks in `~/.claude/settings.json`;
- the hooks of the project the session was launched in, `.claude/settings.json`;
- the hooks of any `--settings` file.

No guard can relax another. mAIcelium's hooks are registered only in the
workspace's own `.claude/settings.json`. They apply to sessions launched in
mAIcelium and are **not** meant to be installed globally.

The hook commands use `"${CLAUDE_PROJECT_DIR:-.}"/…` paths, so they work from
any working directory, and fall back to the working directory when a runner does
not set `CLAUDE_PROJECT_DIR`. On Windows, Claude Code runs command hooks with Git Bash, so
`bin/py.sh` is the launcher there too. `bin/py.cmd` is for running the scripts
by hand from `cmd`.

## Decision contract

Each hook prints at most one decision:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny" | "ask", "permissionDecisionReason": "..."}}
```

- **Allow prints nothing.** An explicit `"allow"` would skip Claude Code's own
  permission prompts, which is not the guard's call.
- **Ask needs a human.** In `claude -p` and in the `dontAsk` permission mode
  there is nobody to confirm, so `ask` behaves as deny. That is expected.
- **Both hooks fail closed.** Invalid stdin or any unexpected exception produces
  a deny with the reason, logged to `.claude/hook-failures.log`. If the
  interpreter cannot start at all, the hook exits non-zero and Claude Code treats
  that as non-blocking. Claude Code ≥ v2.1.295 can make that blocking with
  `"onFailure": "block"` on the hook entry; that setting is left to the user.
- **Every deny says what to do instead:** mount the repo, use the scratchpad,
  confirm the ask, use the package manager, or `mai sync`.

## The write pipeline (`_policy.decide`)

1. **Take the target path:** `file_path`, or `notebook_path` for NotebookEdit.
   A missing, relative or unrepresentable path is a deny. Unrepresentable means
   it contains a NUL byte or a lone surrogate.
2. **Build two identities:**
   - `lexical`: `abspath`;
   - `real`: `realpath`, which also resolves the existing ancestors of a new
     file.
3. **Check the perimeter:** `real` must fall under one of the
   [write roots](#write-roots), otherwise deny.
4. **Apply the [name rules](#name-rules)** to both identities, per path
   component and case-insensitively. A symlink with an innocent name cannot
   alias a protected file, and `.CLAUDE/settings.json` is
   `.claude/settings.json`.
5. **The most restrictive decision wins:** deny > ask > allow.

### Write roots

| Root | Source | Condition |
|---|---|---|
| Workspace | `MAICELIUM_ROOT`, or three levels above the hook | always |
| Mounted repos | real path of each direct child of `projects/` and `mesh/layers/`, plus `mesh/mcp` | after the mount filter below |
| Plans | `~/.claude/plans/` | always |
| Project memory | `dirname(transcript_path)/memory/` | only when `transcript_path` is a non-empty absolute path under `~/.claude/projects/`; otherwise a write to `~/.claude/projects/<slug>/memory/…` is an **ask** |
| Scratchpad | the payload's `scratchpad_dir`, exactly | only when the field is present and names an existing real directory. Subagents receive their parent's value. |
| Plain temp | `tempfile.gettempdir()`, `/tmp`, `/private/tmp` | excluding everything under a `claude-*` folder there (task output and other harness state), except the scratchpad above |

**Mount filter.** A mount target is never a root when it is:
- a disk or drive root;
- `$HOME` or a folder containing it;
- the workspace or a folder containing it;
- anything under a hidden folder of `$HOME`, which covers `~/.claude`, `~/.ssh`
  and `~/.aws`.

`projects/`, `mesh/` and `mesh/layers/` must be real directories. If one is a
symlink, nothing under it is trusted: otherwise `ln -s ~ projects` would make
all of `$HOME` writable.

Other mount rules:
- Mounts are discovered from the filesystem, never from `WORKSPACE.md`.
- Dangling links and links to files are ignored.
- Duplicate links to one repo, or one repo that is both a project and a layer,
  are fine.

Layer reflections (`mesh/skills/_*/…`, `mesh/rules/_*/…`) are not a special case.
Their real path falls inside the layer's root. A real file there, one that does
not resolve into a layer, is a stale reflection and is denied with the
instruction to edit the layer and run `mai sync`.

### Name rules

These apply inside any root, at any depth, on both identities.

| Pattern | Decision | Notes |
|---|---|---|
| `.env`, `.env.*` | deny | names ending in `.example`, `.sample` or `.template` are allowed |
| any `.git` component (directory or pointer file) | deny | for a commit message, write it to the scratchpad and use `git commit -F <path>` |
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Pipfile.lock` | deny | use the package manager |
| `.claude/settings*.json` (workspace or any project) | ask | an agent's own permissions and hooks |
| `.sops.yaml` | ask | decides who can decrypt the secrets |
| `*.pem`, `*.key`, `*.p12`, `*.pfx`, `kubeconfig`, `*.kubeconfig` | ask | key or credential material; overwriting it is destructive |
| `bin/hooks/**/*.py`, `bin/py.sh`, `bin/py.cmd` (workspace only) | ask | the guards themselves; a mounted repo's own `bin/hooks/` is ordinary code |
| `WORKSPACE.md`, `mAIcelium.code-workspace`, `.claude/projects-context.md`, `.claude/skills/`, `.cursor/`, `.agents/`, `.antigravity/` | deny | workspace root only; auto-generated |

**Matching is case-insensitive on every platform**, Linux included. On macOS and
Windows, `.ENV` and `.Git/` are the same file as their lowercase forms. On
Linux they are different files, but there is no legitimate reason to create
them, so they are treated the same on purpose.

## `guard_bash`

`guard_bash` has three layers.

### 1. Patterns on commands, not data

Before any pattern runs, heredoc bodies are dropped. A heredoc operator inside
quotes is ignored, so `echo "<<X"` cannot hide the next line.

The pattern rules are:
- `rm -rf` on dangerous targets, evaluated per segment and at command position;
- destructive SQL;
- force push to `main`/`master`;
- `mkfs`/`dd`;
- `chmod 777`.

`chmod 777`, force push and `mkfs`/`dd` match on the command with quoted phrases
blanked. A quoted single word stays a word, so `git push --force origin "main"`
still blocks. The SQL rule keeps quoted text, because SQL is normally passed
quoted to a client (`psql -c "..."`).

This layer is a speed-bump: variable indirection, command substitution and
unlisted wrappers bypass it. The module docstring lists the known gaps.

### 2. Destinations through the write policy

Every redirection target (`>`, `>>`, `>|`, `&>`, `&>>`, `>& file`) and every
`tee` argument is resolved and checked by `_policy.decide`:
- relative targets are resolved against the payload `cwd`;
- `~` and `$HOME` are expanded;
- targets with other variables, globs or command substitution are not resolved.

Who produced the bytes decides how a protected name is treated:

| Producer | Protected name | Outside the roots |
|---|---|---|
| agent content: a heredoc (`<<`, `<<-`), a herestring (`<<<`), `echo` or `printf` | the same decision and message as Write (`cat <<EOF > .env` → deny) | deny |
| anything else: program output (`./tool.py > .env`, `sops -d x \| tee .env`) | ask: the secret never passed through the agent, but the destination is sensitive | deny |

For `tee`, the producer is the pipeline stage right before it.

The principle: a secret must not pass through the agent's context. A script the
agent writes and then runs to handle secrets keeps working, and what it does
inside (`open(".env", "w")`) is not visible to the hooks.

**Heredocs to files inside the roots are allowed.** That is the easy path now
that `Write` works on mounted repos, and its use is being measured.

### 3. Mounts and guard files

- **`ln` into `<ws>/projects/` or `<ws>/mesh/` is denied.** That covers the last
  operand, `-t`/`--target-directory`, and a single operand with the cwd inside
  one of those folders. A hand-made link there would become a write root. Use
  `mai add <name> <path>`, `mai add-layer <name> <path>` or
  `mai add-mcp <path>`.
- **Write verbs on guard files are denied.** This applies to a simple command
  (pipeline stage) that names `bin/hooks/**/*.py`, `bin/py.sh`, `bin/py.cmd` or
  the workspace's `.claude/settings*.json` and uses one of these:
  - `sed -i`;
  - `cp`, `mv`, `rm`, `chmod`, `truncate`, `install`, `patch` or `tee`;
  - `git checkout … --` or `git restore`;
  - a `>`/`>>` redirection into it.

  Reading stays allowed: `cat`, `grep`, `rg`, `git diff`, `pytest`. These files
  change only through Write/Edit, where the user confirms each change. Copying
  *from* a guard file is denied too, because the rule only looks at the names.

`Bash(ln:*)` and `Bash(rm:*)` are not pre-approved, so they go through Claude
Code's permission prompt.

## Other security models on the same machine

Several guard systems can run on one machine. They meet only through hook
stacking.

| Model | Scope | What it protects |
|---|---|---|
| Machine-wide hooks of the personal mesh layer (`~/.claude/settings.json`) | every session on the machine | tool-specific guards, such as the Terraform binary in use and chat posting |
| mAIcelium guards (this document) | sessions launched in the mAIcelium workspace | perimeter of mounts plus name rules |
| Agent orchestrations launched with their own `--settings` | those runs only | per-role allow/deny lists, escalation to a coordinator; they forbid heredocs and run unattended (`dontAsk`) |
| Unattended runners (`claude -p`) with their own guard | those runs only | an allow-list of roots, failing closed |

mAIcelium's guards and an orchestration's guards never share a session. The
orchestrations' heredoc ban stays where it is: those runs are unattended and
write infrastructure code. In mAIcelium, heredocs inside the roots are allowed
and measured.

## Other agent environments

mAIcelium is meant to work with several agent environments. Its guards are
written as Claude Code hooks, and today neither of the other two environments
has a guard of its own from mAIcelium.

**Cursor** runs Claude Code hooks by import. By default it loads the hooks of
`.claude/settings.json` (Settings > Agents > Third-Party Imports) and maps
`PreToolUse` to its own `preToolUse`. So in a Cursor agent session opened on the
workspace, the mAIcelium guards may run, but with Cursor's tool names and
payloads. Whether they work there is still to be verified. The known risks and a
manual test procedure are tracked in #49. Cursor's own limits also
apply:
- there is no hook before a file edit, only `preToolUse` and `afterFileEdit`;
- `ask` is not enforced on `preToolUse`.

**Antigravity** reads `.agents/` (rules, skills, `hooks.json`) but nothing from
`.claude/`, so none of the mAIcelium guards run there.

Native adapters for both environments are planned in #50. They would
put a thin layer over `_policy.decide()`, generated into `.cursor/hooks.json`
and `.agents/hooks.json` by `sync_symlinks.py`.

## Residual risks

Accepted or mitigated, but not closed:

- **Bash can still write anywhere** through what it runs: `cp`, `mv`, `git`,
  `python -c "open('.env','w')"`, `python -c "…" > .env`. Only heredoc,
  herestring, `echo` and `printf` count as agent content, so other producers
  writing to a protected name are an ask, not a deny.
- **`guard_bash` reads the command text only:**
  - it does not track cwd changes inside the command (`cd projects && ln -s ~ x`);
  - it does not resolve variables, globs or command substitution in targets;
  - a heredoc fed to an interpreter (`psql <<EOF`) is treated as data.
- **Symlink detection is mitigated, not closed.** The agent can create symlinks
  in forms the `ln` rule does not recognise (`python -c "os.symlink(…)"`,
  `cp -s`). The mount filter and the real-directory requirement on `projects/`,
  `mesh/` and `mesh/layers/` limit what such a link can open.
- **`ask` relies on the user reading what they confirm.**
- **Failing closed blocks every write and command if a guard has a bug.** The
  CI matrix and the crash tests cover this. `.claude/hook-failures.log` holds
  the details.
- **The guards' own failure to start** (missing interpreter, timeout) is
  non-blocking unless `"onFailure": "block"` is set. See
  [Decision contract](#decision-contract).
- **Relocated auto-memory is not supported yet.** `autoMemoryDirectory` and
  `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` are not used today.
- **`scratchpad_dir` has only been verified in cloud sessions.** If a local
  `claude -p` does not send it, the scratchpad is denied, not opened.
- **Duplicate links to one repo, and a repo that is both a layer and a project,**
  work but are untidy. Cleaning them up is out of scope.
- **The machine-wide hooks of the personal mesh layer have no CI.** They live
  outside this repo (see #43).

## Measuring

`bin/hook_metrics.py` reads the local Claude Code transcripts and prints, per
month:
- guard denials: `write_denied`, how many of those were perimeter denials
  (`write_denied_outside`), and `bash_denied`;
- the number of Bash commands that use a heredoc.

By default it counts only sessions launched in this workspace; `--all` counts
every session.

Run it before and some weeks after a change to the policy to see whether
denials dropped and whether `Write`/`Edit` replaced heredocs as the way to write
files:

```bash
bin/py.sh bin/hook_metrics.py --since 2026-10
```

## Testing hooks

`tests/test_hooks.py` runs each hook as a subprocess with a JSON payload on
stdin. Two environment overrides keep the tests hermetic:
- `MAICELIUM_ROOT` sets the workspace root;
- `MAICELIUM_TMP_ROOTS` (separated by `os.pathsep`) replaces the plain temp
  roots. pytest's `tmp_path` lives under the system temp dir, which would
  otherwise be a write root.

Symlink tests use `@requires_symlink`. The CI matrix (ubuntu and windows, Python
3.11 and 3.12) fails on any skipped test.
