---
name: testing
description: >-
  When writing tests, reviewing test coverage, designing a test strategy, or evaluating whether existing tests are sufficient.
---
# Testing Skill

## When to use
When writing tests, reviewing test coverage, designing a test strategy,
or evaluating whether existing tests are sufficient.

## Test taxonomy
| Type        | Scope                     | Speed  | When to use                        |
|-------------|---------------------------|--------|------------------------------------|
| Unit        | Single function/class     | Fast   | Business logic, pure functions     |
| Integration | Multiple components + I/O | Medium | Database queries, API endpoints    |
| E2E         | Full user flows           | Slow   | Critical paths, smoke tests        |

Prefer unit tests for coverage breadth. Use integration and E2E tests for
confidence at system boundaries.

## Test structure
Follow **Arrange-Act-Assert**:
1. **Arrange** — set up inputs and dependencies.
2. **Act** — call the function or trigger the behavior.
3. **Assert** — verify the expected outcome.

One logical assertion per test. Test names describe behavior:
`test_expired_token_returns_401`, not `test_validate_token`.

## What to test
- Business logic and domain rules.
- Edge cases: empty inputs, nulls, boundary values, error paths.
- Pure functions first — they are inherently testable
  (ref: `coding-standards.md`).
- Boundary validation — validate at the edges
  (ref: `architecture-principles.md`).

## What NOT to test
- Framework internals or standard library behavior.
- Getter/setter boilerplate with no logic.
- Third-party library behavior (trust their tests).
- Implementation details that may change without affecting behavior.

## TDD workflow (Red-Green-Refactor)
1. **Red** — write a failing test that defines the expected behavior.
2. **Green** — write the minimal code to make the test pass.
3. **Refactor** — clean up while keeping tests green.

Use TDD when: the requirements are clear, building business logic,
or fixing a bug (write the failing test first, then fix).

## Multi-project test runner detection
Each project in `projects/` may use a different runner. Check for:
- `package.json` → `npm test` or `npx jest`
- `pyproject.toml` / `pytest.ini` → `pytest`
- `Makefile` → `make test`
- `Cargo.toml` → `cargo test`
- `go.mod` → `go test ./...`

Run the project's own test command — do not assume a global runner.

## Coverage strategy
- Aim for meaningful coverage, not a percentage target.
- Critical paths must have tests. Happy path + main error path minimum.
- New code should include tests. Bug fixes should include a regression test.
- Untested legacy code: add tests before modifying, not retroactively for all.
