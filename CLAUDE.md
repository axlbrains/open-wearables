# CLAUDE.md

Please follow the guidelines and project structure defined in ./AGENTS.md

For Cursor and other agents: Refer to .cursor/rules/ for detailed configuration.

## Repo & fork layout

- This checkout is the **`axlbrains/open-wearables`** fork (remote `origin`); upstream is **`the-momentum/open-wearables`** (remote `upstream`). Our issues/PRs live in the **axlbrains** fork — when asked to look at "our" issues/PRs, use `--repo axlbrains/open-wearables`, not upstream.
- Active integration branch is **`axl-integration`** (carries axl-specific prod customizations on top of upstream `main`). Backend lives in `backend/`.
- **Versioning is an independent fork line, ahead of upstream.** Prod ran `0.6.x` while upstream's latest release was `0.5.2`. Don't "sync" the version down to upstream — bump our own line (e.g. `0.6.5 → 0.6.6`).

## Upstream sync

- `.github/workflows/upstream-sync.yml` runs weekly (Mon 06:00 UTC, cron `0 6 * * 1`); GitHub delays it ~1–1.5h. The `main` leg opens a PR; the **`axl-integration` leg routinely fails on merge conflicts** and needs a manual merge — this is by design, not a regression.
- Recurring conflict file: `backend/app/repositories/event_record_detail_repository.py`. Resolution convention: **keep our `create_and_flush()` that routes through `bulk_create` (`INSERT … ON CONFLICT DO UPDATE`)** over upstream's savepoint/`IntegrityError` variant — we avoid Postgres ERROR-log noise. Drop the now-unused `IntegrityError` import if you take our side.
- **After every sync, run `alembic heads` (in `backend/`).** Upstream and our branch routinely add migrations off the same parent, leaving **two unmerged heads**. `alembic upgrade head` (what the prod init job runs) then fails with "Multiple head revisions present" and **migrations silently stop applying** — which already shipped a prod image whose code queried a column the DB never got (`provider_settings.webhook_secret`), 500ing `/connections` with no traceback (axlbrains/open-wearables#22). If >1 head: `alembic merge -m "merge heads" <rev1> <rev2>`, commit, and on prod apply the lagging branch with `alembic upgrade heads` (plural) before re-running the init job.

## CI / local dev

- `ci.yml` triggers **only on push to `main` and on pull_request** (paths-filtered). **Pushing to `axl-integration` does NOT run CI** — open a PR to get tests. So local pushes to the integration branch are unvalidated.
- Backend tests need **Docker** (testcontainers spin up Postgres + Redis in `conftest.py`); they can't run in a Docker-less sandbox. CI provides Postgres as a service + env (`ENV=test`, `SECRET_KEY`, base64 `MASTER_KEY`).
- No `uv` preinstalled in some envs: `pip install --user uv` then `uv sync`. To import the app / run non-DB tests locally set `ENV=test SECRET_KEY=… MASTER_KEY=<base64>`.

## Prod infra (GCP project `axl-platform-prod`, region `europe-west1`)

- Cloud Run services: `open-wearables-prod-api`, `open-wearables-prod-worker`; job `open-wearables-prod-init`. Image repo: `europe-west1-docker.pkg.dev/axl-platform-prod/open-wearables-prod/backend:<semver>`.
- **There are NO Cloud Build triggers.** Prod images are built + deployed manually with semver tags (the `SHORT_SHA` flow in `backend/cloudbuild.yaml` is unused for prod). Release recipe:
  1. `gcloud builds submit backend --config <cfg> ...` building with `--build-arg APP_VERSION=<ver>` (bakes the real version into the image).
  2. `gcloud run services update {open-wearables-prod-api,open-wearables-prod-worker} --image …:<ver>` and `gcloud run jobs update open-wearables-prod-init --image …:<ver>`.
- **⚠️ Terraform WILL clobber a manual image deploy.** `.github/workflows/terraform-deploy.yml` runs `terraform apply` on every **push to `axl-integration`/`main` touching `infra/gcp/terraform/**`** (auth as `github-terraform@`). It materializes the gitignored `TFVARS_PROD` repo secret as `terraform.tfvars`, and `image = var.backend_image` pins the Cloud Run image. That pin lagged the manual semver line (secret held `0.5.15` while prod ran `0.6.x`), so an unrelated infra change (e.g. a `cloud_run.tf` edit) silently **reverts api+worker+init to the pinned image** — dropping whatever was manually deployed (this regressed `/health` once). After any infra apply, re-check `/health` and re-deploy the intended `:<ver>` if needed. **The durable fix is to bump `backend_image` in the `TFVARS_PROD` secret** (and the committed `environments/prod/terraform.tfvars`, currently a stale `0.5.6` placeholder) whenever you cut a new prod version — only an org owner can edit the secret.
- `GET /health` → `{"status":"ok","version":"<ver>"}`; version comes from `APP_VERSION` build arg → ENV → `settings.app_version`, and also feeds FastAPI `info.version` (fixes the stale `0.1.0` in `/openapi.json`). Consumed by `status.axl.coach`'s `wearables-sync` tile.

## ⚠️ Observability gotcha (cost us a long debug; root cause of #22)

- **`cpu_idle = true` (CPU throttling) on a low-traffic Cloud Run service silently drops ALL container stdout/stderr from Cloud Logging** — only the infra-written request logs survive. The instance is throttled to ~0 CPU the moment a request finishes, before the log-export pipeline flushes. Symptom: a 500 (or any error) with **no traceback anywhere**, despite the app logging correctly.
- Fix = **`cpu_idle = false`** (CPU always allocated) — set in `infra/gcp/terraform/modules/open_wearables_stack/cloud_run.tf` for api+worker; live-applied with `gcloud run services update <svc> --no-cpu-throttling`.
- **Red herrings that are NOT the cause:** stdout buffering (`PYTHONUNBUFFERED` — already set), and the runtime SA missing `roles/logging.logWriter` (Cloud Run ships container logs via the service agent, not the runtime SA — verified: `axl-av-prod` logs fine with no logging role). A continuously-polled service (e.g. health checks) masks the bug because CPU never idles. Cloud Run **Jobs** always have CPU, so they log fine and are a good probe.
- Logging exclusions live on the **`_Default` sink** (not `gcloud logging exclusions`): `exclude-ow-2xx-access-logs` drops 2xx *request* logs for OW api+worker; others drop health-check/cron 2xx and scanner 404s. They key on `httpRequest.status` so they do not touch app stdout.
- App logging: `app/utils/structured_logging.py` `log_structured()` does `print(json, file=sys.stdout, flush=True)`. `app/main.py` reconfigures root logging to stdout and adds a global `Exception` handler that logs the traceback before returning 500 (so prod 5xx are root-causable once logs flow). In prod a `UvicornAccess2xxFilter` drops happy-path 2xx access lines.
