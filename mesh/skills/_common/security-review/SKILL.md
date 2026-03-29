# Security Review Skill

## When to use
When reviewing code with security implications: authentication, payment handling,
data processing, API endpoints, dependency updates, Docker configurations,
or before deploying to production.

This skill is an **active analysis process**. For a quick pre-commit checklist,
see `mesh/rules/_domains/software/security-checklist.md`.

## Step 1: Map the attack surface
Identify all entry points where untrusted data enters the system:
- HTTP endpoints (request params, headers, body).
- CLI arguments and environment variables.
- File inputs (uploads, config files).
- Database queries (stored data rendered back to users).
- Third-party API responses.

For each entry point, trace the data flow: where does user input travel?

## Step 2: Threat model (STRIDE)
For each entry point, evaluate applicable threats:

| Threat                   | Question                                           |
|--------------------------|-----------------------------------------------------|
| **S**poofing             | Can an attacker impersonate a user or service?      |
| **T**ampering            | Can data be modified in transit or at rest?          |
| **R**epudiation          | Can actions be performed without audit trail?        |
| **I**nformation Disclosure | Can sensitive data leak via errors, logs, responses?|
| **D**enial of Service    | Can the system be overwhelmed or crashed?           |
| **E**levation of Privilege | Can a user gain unauthorized access?               |

Not all threats apply to every entry point — focus on relevant ones.

## Step 3: Dependency audit
Check for known vulnerabilities in dependencies:
- **Node.js**: `npm audit` or `npx auditjs`
- **Python**: `pip-audit` or `safety check`
- **Docker**: `trivy image <image>` or `grype <image>`
- **General**: check CVE databases for critical dependencies.

Flag: outdated packages, abandoned packages, packages with known CVEs.

## Step 4: Code-level analysis
Look for common vulnerability patterns:
- **Injection**: SQL concatenation, command injection, path traversal.
- **Authentication bypass**: missing auth checks, hardcoded credentials.
- **Authorization flaws**: missing RBAC checks, IDOR vulnerabilities.
- **Data exposure**: secrets in logs, verbose error messages, PII leaks.
- **Insecure cryptography**: MD5/SHA1 for passwords, weak random generators.
- **Race conditions**: TOCTOU bugs, concurrent state mutations.

## Step 5: Configuration review
Check infrastructure and deployment configuration:
- Ref: `security-checklist.md` for the full list (CORS, CSP, HSTS, secrets).
- Debug mode disabled in production.
- No default credentials.
- TLS/HTTPS enforced.
- Container runs as non-root user (ref: `security-checklist.md` Docker section).

## Step 6: Report
Classify each finding:

| Severity   | Criteria                                          |
|------------|---------------------------------------------------|
| **Critical** | Exploitable now, high impact (data breach, RCE) |
| **High**     | Exploitable with effort, significant impact     |
| **Medium**   | Defense-in-depth gap, moderate impact            |
| **Low**      | Best practice violation, minimal impact          |

For each finding document: description, file and line, impact, remediation.
