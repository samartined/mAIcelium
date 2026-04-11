---
name: devops
description: >-
  When working with Docker, CI/CD pipelines, infrastructure configuration, container security, or deployment processes.
---
# DevOps Skill

## When to use
When working with Docker, CI/CD pipelines, infrastructure configuration,
container security, or deployment processes.

## Dockerfile best practices

### Build optimization
- **Multi-stage builds** — separate build dependencies from runtime image.
- **Minimal base images** — prefer `alpine`, `slim`, or `distroless` variants.
- **Layer ordering** — copy dependency files first (`package.json`, `requirements.txt`),
  install dependencies, then copy application code. This maximizes cache hits.
- **Combine RUN commands** — reduce layers with `&&` chains for related operations.
- **Use `.dockerignore`** — exclude `.git/`, `node_modules/`, `__pycache__/`, tests, docs.

### Security (ref: `security-checklist.md` Docker section)
- **Non-root USER** — always add a `USER` directive after installing dependencies.
- **Pin versions** — use specific base image tags, not `latest`.
- **No secrets in build** — never `COPY .env` or pass secrets via `ARG`/`ENV`.
  Use runtime injection or secret mounting (`--mount=type=secret`).
- **HEALTHCHECK** — add a health check for orchestrators to monitor container state.
- **Read-only filesystem** — run with `--read-only` where possible, use tmpfs for `/tmp`.

## Docker Compose
- Define services with explicit `image` or `build` context.
- Use named networks for service isolation.
- Use named volumes for persistent data — never bind-mount sensitive host paths.
- Secrets via environment variables from `.env` file (never hardcoded in compose).
- Use `depends_on` with `condition: service_healthy` for startup ordering.
- Set `restart: unless-stopped` for production services.

## CI/CD pipeline structure
Order stages by cost (cheapest first, fail fast):
1. **Lint** — static analysis, formatting checks.
2. **Test** — unit tests, then integration tests.
3. **Build** — compile, bundle, create artifacts.
4. **Scan** — security scanning (trivy, SAST, dependency audit).
5. **Deploy** — push to staging, then production.

Best practices:
- Cache dependencies between runs (node_modules, pip cache, cargo registry).
- Pin action/tool versions (e.g., `actions/checkout@v4`, not `@latest`).
- Use matrix builds for multi-platform support.
- Separate staging and production deployment steps with manual approval.

## Container security scanning
- **trivy** — scan images for OS and library vulnerabilities:
  `trivy image --severity HIGH,CRITICAL <image>`
- **grype** — alternative scanner: `grype <image>`
- **hadolint** — Dockerfile linter: `hadolint Dockerfile`
- Integrate scanning into CI pipeline (stage 4).
- Block deployment on CRITICAL findings.

## Infrastructure patterns
- **Configuration via environment variables** — never hardcode
  (ref: `architecture-principles.md`).
- **Structured logging** — JSON format with appropriate levels
  (ref: `architecture-principles.md`).
- **Stateless design** — store state in external services (DB, cache, queue).
- **Resource limits** — set CPU and memory limits for containers.
- **Health endpoints** — `/healthz` (liveness) and `/readyz` (readiness).

## Monitoring checklist
- [ ] Health endpoints respond correctly.
- [ ] Structured logs include request IDs for tracing.
- [ ] Alerts configured for error rate spikes.
- [ ] Resource usage dashboards available.
- [ ] Secrets rotated on a schedule.
