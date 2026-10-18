# Google Cloud Terraform Overlay

This directory contains the Google Cloud deployment overlay for the `axl-integration` fork.

The design goal is to keep infrastructure changes isolated from the upstream Open Wearables application so that upstream merges stay manageable.

## Principles

- Keep GCP-specific changes additive.
- Preserve the default Docker Compose and Celery workflow used by upstream.
- Move deployment-specific logic into Terraform, startup scripts, and environment flags.
- Replace scheduling and async delivery in phases instead of rewriting task business logic.

## Layout

```text
infra/gcp/terraform/
├── environments/
│   ├── dev/
│   └── prod/
└── modules/
    └── open_wearables_stack/
```

## Scope of the initial scaffold

The initial Terraform scaffold focuses on shared control-plane resources that are safe to add without rewriting application behavior:

- required Google APIs
- Artifact Registry
- dedicated service accounts
- Cloud Tasks queues
- Cloud Scheduler jobs
- optional Secret Manager secret placeholders
- VPC network, subnet, and Serverless VPC Access connector
- Cloud SQL PostgreSQL instance, database, and application user
- Memorystore Redis instance
- Cloud Run backend API service
- Cloud Run internal worker service
- Cloud Run backend init job
- Cloud Run frontend service

The backend code now also includes a dispatcher abstraction and an internal worker task API so the same repository can support:

- upstream-compatible `Celery` dispatch in local and existing environments
- `Cloud Tasks` dispatch in the GCP overlay

## Usage

Initialize a specific environment:

```bash
cd infra/gcp/terraform/environments/dev
terraform init
terraform plan -var-file=terraform.tfvars
```

The `terraform.tfvars.example` file in each environment shows the expected variables. Copy it to `terraform.tfvars` locally and fill in real values.

## Recommended rollout

Use a two-step apply for Cloud Tasks:

1. Apply with `enable_cloud_tasks_dispatch = false`.
2. Read the worker URL from Terraform outputs.
3. Set `worker_service_base_url` to that URL.
4. Re-apply with `enable_cloud_tasks_dispatch = true`.

This keeps the worker URL outside the core application code and avoids self-referential Cloud Run configuration during the first apply.

## Notes on compatibility

- The Terraform here should not remove or replace Railway-specific files.
- Cloud Run entrypoints live alongside the existing startup scripts instead of replacing them.
- Celery remains the compatibility default until a dispatcher abstraction is introduced in the backend.
