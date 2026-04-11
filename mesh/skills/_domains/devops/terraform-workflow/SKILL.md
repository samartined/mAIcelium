# Terraform Workflow

## When to use
When analyzing, writing, reviewing, or planning Terraform IaC changes — for any GCP project
in this workspace. This skill defines the complete lifecycle including mandatory human gates.

## Division of responsibility

| Action | Who |
|--------|-----|
| Read and analyze existing code | Agent |
| Write Terraform code | Agent |
| Run `terraform validate` | Agent (read-only verification) |
| Run `terraform init` | Agent (with explicit instruction) |
| Run `terraform plan` | Agent (with explicit instruction) |
| Run `terraform apply` | **HUMAN ONLY — always** |
| Run `terraform destroy` | **HUMAN ONLY — always** |
| State manipulation (`state mv`, `state rm`, `import`) | **HUMAN ONLY — always** |

## Phase 1: Context Gathering (before writing any code)

1. **Read at least 2–3 existing `.tf` files** of the same resource type in the target repo
2. Document the patterns found:
   - Naming conventions for `resource` blocks and `local` references
   - `format()` string patterns and interpolation style
   - Language used in `display_name`, `description`, and string literals (must be English)
   - Comment presence — usually zero; replicate whatever the repo uses
   - Argument ordering convention (alphabetical vs logical grouping)
3. **Read `settings/*.yaml`** to understand the environment configuration and available locals
4. **Check what currently manages the affected resources** — identify the `.tf` files in scope
5. If the scope is ambiguous — ask the operator before writing code

## Phase 2: Write the Code

Follow `terraform-gcp.mdc` and `gcp-architecture.mdc` conventions:
- Match the existing code style exactly (naming, indentation, `format()` patterns)
- English for all string literals, `display_name`, `description` values
- No Jira ticket IDs in code, names, comments, or labels
- No personal names — use functional role descriptions
- Zero comments unless the logic is genuinely non-obvious
- Use `for_each` instead of `count` when iterating over a map or set with stable keys
- Never hardcode project IDs or regions — use `local.settings.project.id` and `local.settings.region_name`
- Pin module versions with `?ref=vX.Y-YYYYMMDDHHMI`

## Phase 3: Present the Changes (HITL Gate 1)

Present to the operator before proceeding:

```
Files modified:
  - {file1.tf}: added {resource_type}.{name}
  - {file2.tf}: modified {attribute} on {resource_type}.{name}

Resources created:   N (list each)
Resources modified:  N (list each with what changes)
Resources destroyed: N (list EVERY one explicitly — destruction is irreversible)

Risks:
  - {data loss / downtime / IAM escalation / cost increase if applicable}
```

**Wait for explicit approval before proceeding to plan.**

## Phase 4: Plan (HITL Gate 2)

### Multi-team environments: always use `-target`

Real-world IaC repos have multiple operators. Unreviewed or unsynchronized changes
from other sessions accumulate in the state. Running a plain `terraform plan` in this
context risks surfacing — and later applying — changes that were **not introduced in
this session**, including destructive ones.

**Default approach: scope the plan to the exact resources being changed.**

The agent proposes the `-target` flags based on the resources written in Phase 2:

```bash
cd {repo_dir}
terraform workspace select {env}
terraform init          # only if providers or modules changed

# Scoped plan — targets only the resources introduced in this session
terraform plan -out=tfplan.bin \
  -target=google_cloud_run_v2_service.api \
  -target=google_project_iam_member.sa_secret_access \
  2>&1 | tee /tmp/tf-plan-$(date +%Y%m%d-%H%M%S).txt
```

This prevents a stale or drifted resource — modified by another operator, a broken
pipeline, or a manual console change — from sneaking into the apply scope.

Use a full `terraform plan` (no `-target`) only when:
- The intent is explicitly to reconcile **all** drift in the workspace
- The operator confirms they want to see and apply everything
- It is a dedicated drift-review session

### Reviewing the plan output

- Confirm the plan contains **only** the resources listed in the Phase 3 proposal
- If unexpected resources appear in the scoped plan → STOP, investigate, do not proceed
- If `-target` misses a dependency Terraform requires → add the dependency target, re-plan
- Note the counts: `Plan: N to add, N to change, N to destroy` must match expectations exactly

**Wait for operator to confirm the plan is correct before proceeding.**

## Phase 5: Apply — Human Executes

The agent DOES NOT run apply. The operator runs:

```bash
terraform apply tfplan.bin
```

While the operator applies, the agent:
- Explains what each step means as it appears
- Helps interpret errors if apply fails

If apply fails:
1. Read the full error output
2. Diagnose the root cause
3. Propose a code fix — do NOT suggest re-running apply automatically
4. Return to Phase 2 with the fix

## Phase 6: Verify

After apply completes:
- Provide the operator with verification commands (e.g., `gcloud run services describe`, `gcloud iam service-accounts list`)
- Confirm the intended behavior is working
- Watch Cloud Monitoring for error rate spikes in the first 5 minutes

## Workspace commands reference

```bash
# Know which workspace is active
terraform workspace show

# Switch workspace explicitly (always confirm before plan/apply)
terraform workspace select pre    # or pro

# Validate code syntax (safe — no state modification)
terraform validate

# Format code
terraform fmt -recursive

# Check for drift without state lock (read-only)
terraform plan -refresh-only
```

## Common errors

| Error | Diagnosis |
|-------|-----------|
| `Error acquiring state lock` | Another apply in progress or crashed. Confirm no apply is running before `terraform force-unlock` — HITL required. |
| `Error 403: Permission denied` | Service account missing IAM role. Identify minimum role needed and propose binding. |
| `Error: Resource already exists` | Resource exists outside Terraform state. Use `terraform import` — HITL required. |
| `Error: Cycle in dependency graph` | Circular reference between modules/resources. Refactor to break the cycle. |
| `Error: Invalid index` | `for_each` key not found. Check settings YAML for missing entries. |

## Patterns to avoid

- Do NOT use `lifecycle { prevent_destroy = true }` on everything — only stateful resources (Cloud SQL, GCS with data)
- Do NOT use `-target` to work around dependency issues — fix the dependency instead; `-target` is for **scope isolation**, not for hiding broken module graphs
- Do NOT inline sensitive values — reference Secret Manager secrets at runtime
- Do NOT use `count` when `for_each` is cleaner and keys are stable
- Do NOT leave `tfplan.bin` files in the repo (add to `.gitignore`); `.terraform.lock.hcl` should be committed
