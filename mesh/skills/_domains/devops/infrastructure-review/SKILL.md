# Infrastructure Review

## When to use
When reviewing Terraform code, PRs with IaC changes, or auditing existing
infrastructure configuration. Use this skill for any GCP IaC review in this workspace.

## Process

### Step 1: Scope the review

- Identify the affected GCP projects and environments (pre, pro, ops)
- List all resource types being created, modified, or destroyed
- Note which files are changing and which are unchanged

### Step 2: Security checklist

**IAM**
- [ ] No primitive roles (`roles/owner`, `roles/editor`) granted to workload identities
- [ ] No wildcard IAM bindings (`allUsers`, `allAuthenticatedUsers`)
- [ ] Service accounts have the minimal required roles
- [ ] No `google_service_account_key` resources created (absent or explicitly justified)
- [ ] Workload Identity Federation used for CI/CD — not SA JSON keys
- [ ] IAM bindings scoped at the narrowest resource level, not project-wide when avoidable

**Networking**
- [ ] No `0.0.0.0/0` in firewall ingress rules without documented justification
- [ ] Cloud Run services have a VPC connector if they access private resources
- [ ] No public IPs (`ipv4_enabled = true`) on Cloud SQL instances in production
- [ ] GCS buckets have `public_access_prevention = "enforced"` unless explicitly public

**Secrets**
- [ ] No secrets hardcoded in `.tf` files
- [ ] SOPS encryption present for `secrets/` directory if it exists
- [ ] Secret Manager used for runtime secrets — not environment variables with plaintext values
- [ ] No `.tfvars` files with sensitive values committed

**State**
- [ ] Backend is GCS (`backend "gcs"`) — never local state
- [ ] State bucket has versioning enabled
- [ ] State prefix separates environments

### Step 3: Convention checklist

**Naming**
- [ ] Resource names follow `{purpose}-${terraform.workspace}` pattern
- [ ] Labels include `env`, `service`, and at minimum one ownership identifier
- [ ] File names follow `<domain>.<resource_type>.tf`
- [ ] All `display_name`, `description`, and string literals are in English
- [ ] No Jira ticket IDs in any resource attribute, label, or comment

**Code quality**
- [ ] `for_each` used instead of `count` where iteration is over stable keys
- [ ] No hardcoded project IDs — uses `local.settings.project.id`
- [ ] No hardcoded regions — uses `local.settings.region_name`
- [ ] Module versions pinned with `?ref=vX.Y-YYYYMMDDHHMI`
- [ ] No commented-out code blocks left in
- [ ] `terraform fmt` applied (consistent indentation, argument alignment)

**Settings**
- [ ] Per-environment differences live in `settings/{env}.yaml`, not scattered in `.tf` files
- [ ] `default.yaml` holds safe base values that the per-env YAML overrides

### Step 4: Cost and scaling review

- [ ] Cloud Run `max_instance_count` set — unbounded auto-scaling is a cost risk
- [ ] Cloud SQL tier is appropriate for each environment (not prod-sized in pre)
- [ ] BigQuery tables have partition expiration where data volume warrants it
- [ ] GCS lifecycle policies defined for buckets that accumulate data over time

### Step 5: Identify risks

For each finding, document:

| Field | Content |
|-------|---------|
| Resource | Which `resource.type.name` is affected |
| Finding | What the issue is |
| Severity | Critical / High / Medium / Low |
| Remediation | Concrete fix |

### Step 6: Review output

Present findings grouped by priority:
1. **Security** — any Critical or High severity (blocking; must fix before merge)
2. **Conventions** — violations of naming or code style (should fix before merge)
3. **Cost** — scaling and cost risks (informational, flag for discussion)
4. **Recommendations** — optional improvements

## When to block a merge

Block if any of the following are present:
- Critical or High severity security finding
- Hardcoded credentials, tokens, or API keys anywhere in the diff
- Missing GCS state backend (local state)
- Unencrypted secrets or SOPS bypass
- Wildcard IAM bindings (`allUsers` / `allAuthenticatedUsers`)
- `terraform destroy` of production stateful resources without explicit approval trail

## Quick reference: severity guide

| Severity | Examples |
|----------|---------|
| Critical | Hardcoded secret, public Cloud SQL, `allUsers` IAM, open 0.0.0.0/0 firewall |
| High | Primitive roles granted, SA JSON key creation, no state bucket versioning |
| Medium | Missing labels, wrong environment tier, no partition expiration on large tables |
| Low | Non-standard naming, missing `terraform fmt`, suboptimal but safe patterns |
