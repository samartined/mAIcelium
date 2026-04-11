# Incident Response

## When to use
When a production incident is detected, reported, or suspected. This skill covers
triage, investigation, and communication.

The agent's role is **diagnostic and advisory**. All remediations require human execution.

## Severity classification

| Sev | Criteria | Response |
|-----|----------|---------|
| **P1** | Full service outage, data loss, security breach | Immediate — all hands |
| **P2** | Degraded performance, partial outage, multiple users affected | < 30 min |
| **P3** | Minor degradation, workaround available | < 2 hours |
| **P4** | Cosmetic issue, single user affected | Next business day |

Classify severity first. It determines communication cadence and who to loop in.

## Phase 1: Triage (read-only — agent may execute these)

```bash
# Cloud Run service status and recent revisions
gcloud run services describe {SERVICE} --region={REGION} --project={PROJECT}
gcloud run revisions list --service={SERVICE} --region={REGION} --project={PROJECT}

# Recent error logs (last 1 hour)
gcloud logging read \
  'severity>=ERROR AND resource.type="cloud_run_revision"' \
  --freshness=1h --limit=50 --project={PROJECT} --format=json

# Cloud SQL instance status
gcloud sql instances describe {INSTANCE} --project={PROJECT}

# Recent IAM or config changes (audit log)
gcloud logging read \
  'logName="projects/{PROJECT}/logs/cloudaudit.googleapis.com%2Factivity"' \
  --freshness=2h --limit=30 --project={PROJECT}

# Active Cloud Build builds (check for failed deploys)
gcloud builds list --filter="status=FAILURE" --limit=5 --project={PROJECT}
```

## Phase 2: Document findings

Before proposing any remediation, document:

1. **Observed symptoms**: error codes, error messages, latency values, affected endpoints
2. **Affected components**: which services, regions, environments
3. **Start time**: when did the first error appear in logs (find the exact timestamp)
4. **Recent changes**: deployments, Terraform applies, config changes in the last 24 hours
5. **Blast radius**: estimated number of users or requests affected

## Phase 3: Hypothesize

Rank hypotheses (most probable first for GCP/Cloud Run environments):

1. **Recent deployment** — bad container image or configuration change (check revision list)
2. **IAM or permission change** — a role removed or SA deleted (check audit logs)
3. **Upstream dependency failure** — Cloud SQL, Memorystore, or external API down
4. **Resource exhaustion** — max instances reached, memory limit OOM, quota exceeded
5. **Data issue** — schema change, corrupt record causing 500s in a specific code path
6. **GCP platform incident** — check `status.cloud.google.com` for the affected region/service

## Phase 4: Remediation proposals (HITL required for all)

The agent proposes options; the human decides and executes.

For each option, document:
- What it does
- Risk of doing it
- Risk of NOT doing it
- How to verify it worked
- How to roll it back if it makes things worse

**Option A: Traffic rollback** (bad deployment)
```bash
# HUMAN executes — route 100% traffic to previous revision
gcloud run services update-traffic {SERVICE} \
  --to-revisions={PREVIOUS_REVISION}=100 \
  --region={REGION} --project={PROJECT}
```

**Option B: Scale adjustment** (resource exhaustion)
```hcl
# Agent proposes Terraform change — human applies
resource "google_cloud_run_v2_service" "..." {
  template {
    scaling {
      max_instance_count = {NEW_MAX}
    }
  }
}
```

**Option C: Permission fix** (IAM issue)
- Agent identifies the missing binding
- Writes the Terraform code following `gcp-iam` skill
- Human reviews and applies via Terraform workflow

**Option D: Cloud SQL restart** (database unresponsive)
```bash
# HUMAN executes — causes brief downtime
gcloud sql instances restart {INSTANCE} --project={PROJECT}
```

## Phase 5: Communication

Draft a status update for the operator to review and send (do not send automatically):

```
[INCIDENT - P{N}] {Service} — {brief description}

Status: Investigating / Identified / Mitigating / Resolved
Impact: {what's affected, estimated user count}
Start time: {ISO timestamp}
Current action: {what is being done right now}
Next update: {time or event trigger}
```

Update frequency:
- P1: every 15 minutes until resolved
- P2: every 30 minutes until resolved
- P3: at identification and resolution

## Phase 6: Post-incident review

After the incident is resolved:
1. Document the complete timeline: detection → triage → root cause → resolution
2. Identify the root cause (not just the symptom)
3. Propose action items as concrete Terraform or code changes:
   - Alert that would have caught this earlier
   - Runbook step that was missing
   - Code or config fix to prevent recurrence
4. Update the operations bitacora with the full entry
5. If the root cause is reusable knowledge, document it in the project wiki or runbook

## What the agent must NOT do during an incident

- NEVER run `terraform apply` to fix an incident without full HITL approval
- NEVER delete or restart resources assuming it will help without understanding root cause
- NEVER modify IAM bindings without approval, even to "fix" a permission error
- NEVER assume the incident is resolved without explicit verification
- NEVER skip documentation because it feels slow — the timeline is evidence

## Useful dashboards and tools

Check in this order:
1. Cloud Monitoring — Error Rate and Latency dashboards for the affected service
2. Cloud Logging — filter `severity>=ERROR` + service name + time window
3. GCP Status page — `https://status.cloud.google.com`
4. Cloud Trace — latency breakdown to identify slow calls
5. Error Reporting — grouped exceptions with stack traces
