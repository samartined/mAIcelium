# GCP IAM Management

## When to use
When analyzing, proposing, modifying, or auditing IAM bindings in GCP projects.
IAM is a high-sensitivity area — all mutations follow the HITL protocol strictly.

## Principle of least privilege

Before proposing any role grant:
1. Identify the exact GCP API methods the workload needs to call
2. Find the most restrictive predefined role that covers those methods
3. Scope the binding to the narrowest resource possible (secret-level > bucket-level > project-level)
4. Document WHY this role is needed and what would break without it

## Role selection guide

| Use case | Preferred role | Never use |
|----------|---------------|-----------|
| Read GCS objects | `roles/storage.objectViewer` | `roles/storage.admin` |
| Write to GCS | `roles/storage.objectCreator` or `objectUser` | `roles/storage.admin` |
| Read BigQuery data | `roles/bigquery.dataViewer` | `roles/bigquery.admin` |
| Run BigQuery jobs | `roles/bigquery.jobUser` (+ `dataViewer` on dataset) | `roles/bigquery.admin` |
| Deploy Cloud Run | `roles/run.developer` | `roles/run.admin` |
| Invoke Cloud Run | `roles/run.invoker` | `roles/run.admin` |
| Read Secret Manager | `roles/secretmanager.secretAccessor` | `roles/secretmanager.admin` |
| Cloud SQL connect | `roles/cloudsql.client` | `roles/cloudsql.admin` |
| Read logs | `roles/logging.viewer` | `roles/logging.admin` |
| Artifact Registry pull | `roles/artifactregistry.reader` | `roles/artifactregistry.admin` |
| Cloud Build trigger | `roles/cloudbuild.builds.editor` | `roles/cloudbuild.integrations.owner` |

**Never grant to workload service accounts:**
- `roles/owner` — breaks state management if misused; allows self-escalation
- `roles/editor` — too broad; always replaceable with specific roles
- `roles/iam.securityAdmin` — allows self-escalation and granting roles to others

## Service account best practices

- One service account per **workload** (not per developer, not per feature)
- Naming: `{purpose}-{env}@{project}.iam.gserviceaccount.com`
- Grant project-level roles only when resource-level binding is unsupported by the API
- **No JSON keys** — prefer Workload Identity Federation for external systems:

```hcl
# Preferred: Workload Identity Federation
resource "google_service_account_iam_binding" "wi_binding" {
  service_account_id = google_service_account.sa.name
  role               = "roles/iam.workloadIdentityUser"
  members            = [
    "serviceAccount:${var.project}.svc.id.goog[${var.namespace}/${var.ksa_name}]"
  ]
}

# Avoid unless absolutely necessary and explicitly approved:
resource "google_service_account_key" "key" { ... }
```

## Auditing existing bindings (read-only — safe to run)

```bash
# All IAM bindings on a project
gcloud projects get-iam-policy {PROJECT_ID} --format=json

# All service accounts in a project
gcloud iam service-accounts list --project={PROJECT_ID}

# Roles granted to a specific SA
gcloud projects get-iam-policy {PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:{SA_EMAIL}" \
  --format="table(bindings.role)"

# Check if a SA has any JSON keys
gcloud iam service-accounts keys list \
  --iam-account={SA_EMAIL} --project={PROJECT_ID}

# Recent IAM changes (audit log)
gcloud logging read \
  'logName="projects/{PROJECT_ID}/logs/cloudaudit.googleapis.com%2Factivity" AND protoPayload.methodName:"SetIamPolicy"' \
  --freshness=24h --project={PROJECT_ID}
```

## Adding a binding — HITL workflow

1. **Identify** the principal, role, and resource scope
2. **Check** if the binding already exists (avoid duplicates)
3. **Present** the proposed binding for review:

```
Principal: serviceAccount:cb-api-pro@{project}.iam.gserviceaccount.com
Role:      roles/secretmanager.secretAccessor
Resource:  projects/{PROJECT_ID}/secrets/{SECRET_NAME}
Reason:    Cloud Build SA needs to read the SOPS KMS key for secret decryption
```

4. **Wait** for human approval before writing any code
5. **Write the Terraform code** — do NOT run `gcloud add-iam-policy-binding` directly
6. **Show the plan** and wait for apply confirmation from the human

## Common Terraform patterns

```hcl
# Project-level binding (use only when resource-level is not supported)
resource "google_project_iam_member" "sa_bq_viewer" {
  project = local.settings.project.id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Resource-level binding (preferred — more precise)
resource "google_secret_manager_secret_iam_member" "sa_secret_access" {
  secret_id = google_secret_manager_secret.api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runner.email}"
}

# Dataset-level BigQuery binding (preferred over project-level)
resource "google_bigquery_dataset_iam_member" "sa_bq_reader" {
  dataset_id = google_bigquery_dataset.events.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.runner.email}"
}
```

## Detecting over-privileged accounts

Signs of over-privileged service accounts:
- Has `roles/editor` or `roles/owner`
- Has more than 5 project-level role bindings
- Has `roles/*.admin` roles without documented justification
- SA email appears in no active Cloud Run, Cloud Build, or Compute config (potentially orphaned)

When found: propose a least-privilege replacement — do NOT remove the existing binding
immediately. Removing an active binding can cause an outage. Verify usage via Cloud Audit
Logs before proposing removal.

## Identifying unused service accounts

```bash
# List all SAs with their last activity (check if they appear in audit logs)
gcloud logging read \
  'protoPayload.authenticationInfo.principalEmail:{SA_EMAIL}' \
  --freshness=30d --limit=5 --project={PROJECT_ID}
```

If no log entries exist in 30 days, the SA may be unused. Propose removal only after
the human confirms no active workload depends on it.
