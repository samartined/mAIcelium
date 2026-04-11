---
name: backend-python
description: >-
  When writing Python backend code: APIs, scripts, automation, data processing, or CLI tools. Relevant for workspace scripts (`mesh/commands/scripts/`) and Python-based projects.
---
# Backend Python Skill

## When to use
When writing Python backend code: APIs, scripts, automation, data processing,
or CLI tools. Relevant for workspace scripts (`mesh/commands/scripts/`)
and Python-based projects.

## Project structure
Organize by domain/feature, not by file type (ref: `architecture-principles.md`):
```
src/
  auth/
    router.py
    service.py
    models.py
  orders/
    router.py
    service.py
    models.py
  core/
    config.py
    dependencies.py
pyproject.toml          # Single config source
```

Use `pyproject.toml` for project metadata, dependencies, and tool configuration
(pytest, ruff, mypy). Avoid multiple config files when one suffices.

## Code patterns
- **Type hints everywhere** — all function signatures, return types, and variables
  where the type is not obvious. Use `from __future__ import annotations` for
  forward references.
- **Dataclasses or Pydantic** for data models — avoid raw dicts for structured data.
- **Context managers** (`with` statements) for resource management (files, DB connections).
- **Generators** for large datasets — avoid loading everything into memory.
- **Pure functions** whenever possible (ref: `coding-standards.md`).
- **Max 20 lines per function** (ref: `coding-standards.md`).

## Error handling
- Define custom exception hierarchy for the project domain.
- Never bare `except:` — always catch specific exceptions.
- Use `raise NewError("message") from original_error` for exception chaining.
- Log errors with context (what was being attempted, with what inputs).
- Return structured error responses in APIs — never expose stack traces.

## API patterns (FastAPI / Flask)
- **Dependency injection** — use FastAPI's `Depends()` or Flask blueprints.
- **Request validation** — Pydantic models for request bodies and query params.
- **Middleware** for cross-cutting concerns (auth, logging, CORS).
- **Async** where beneficial (I/O-bound operations, concurrent requests).
- **Versioned routes** — `/api/v1/` prefix (ref: `architecture-principles.md`).
- **Consistent responses** — `{ "data": ..., "error": ..., "meta": ... }`
  (ref: `architecture-principles.md`).

## Testing with pytest
- Use **fixtures** for shared setup (`conftest.py` per directory).
- Use **parametrize** for testing multiple input/output combinations.
- Organize: `tests/` mirrors `src/` structure.
- Name tests by behavior: `test_expired_token_raises_unauthorized`.
- Use `pytest-cov` for coverage reporting, not as a target to chase.

## Dependency management
- Use virtual environments: `python -m venv .venv` or `uv venv`.
- Pin all dependency versions in `pyproject.toml` or `requirements.txt`.
- Run `pip-audit` or `safety check` periodically for vulnerability scanning.
- Prefer `uv` for fast installs if available.

## Scripts and CLI tools
For utility scripts (like those in `mesh/commands/scripts/`):
- Use `argparse` for CLI argument parsing.
- Guard the entry point: `if __name__ == "__main__":`.
- Use exit codes: `sys.exit(0)` for success, `sys.exit(1)` for errors.
- Write errors to stderr: `print("Error: ...", file=sys.stderr)`.
- Keep scripts focused — one script, one responsibility.
