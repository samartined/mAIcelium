# Contributing to mAIcelium

This applies to people and to agents.

## Branch flow: feature → `dev` → `main`

```
<type>/<slug>  ──PR──▶  dev  ──release PR──▶  main
```

1. **Branch from `dev`.** Name the branch `<type>/<slug>`, with `type` one of
   `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`, `build`, `ci` or
   `revert`. For example: `fix/guard-write-linked-projects`.
2. **Open the PR against `dev`.** CI must be green on every job, with no skipped
   tests, and the change needs a review before it is merged.
3. **Large changes can be stacked.** Create an integration branch from `dev`,
   open each step as a PR against that branch, then open one PR from the
   integration branch to `dev`.
4. **Release `dev` to `main`.** Open a release PR from `dev` to `main`, usually
   titled `chore(release): vX.Y.Z — …`. It is the **only** kind of PR that
   targets `main`; the `Branch flow` CI check fails any other.
5. **Keep `dev` in step after a release.** Merging the release PR creates a
   merge commit on `main`, so fast-forward `dev` to `main` afterwards:

   ```bash
   git fetch origin && git push origin origin/main:dev
   ```

### Closing issues

GitHub applies `Closes #n` only when a PR merges into the default branch,
`main`:
- PRs into `dev` or into an integration branch reference issues with `Refs #n`;
- the release PR `dev` → `main` carries the `Closes #n` lines for everything it
  ships.

### Hotfixes

There is no shortcut to `main`. An urgent fix goes through `dev` like any other
change, followed by an immediate release PR.

## Commits and PR titles

- **Commits and PR titles:** `type(scope): description`, in lowercase. The
  `PR title` check lints PR titles.
- **Language:** code, commits, PRs and docs are in English (see
  `mesh/rules/documentation-language.mdc`).
- **Public repo:** never write personal paths (`/Users/<name>`) or client names
  in commits, PRs, issues or docs.

## Tests

```bash
python -m pytest -q -m "not install"
```

The CI matrix runs on ubuntu and windows with Python 3.11 and 3.12, and fails on
any skipped test. Tests that need symlinks use `@requires_symlink`; never skip a
test by platform.
