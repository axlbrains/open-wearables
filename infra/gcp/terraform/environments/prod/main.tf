module "open_wearables_stack" {
  source = "../../modules/open_wearables_stack"

  project_id                      = var.project_id
  region                          = var.region
  environment                     = "prod"
  name_prefix                     = var.name_prefix
  labels                          = var.labels
  artifact_registry_repository_id = var.artifact_registry_repository_id
  create_secrets                  = var.create_secrets
  secret_names                    = var.secret_names
  secret_values                   = var.secret_values
  scheduler_jobs                  = var.scheduler_jobs
  create_network                  = var.create_network
  create_cloud_sql                = var.create_cloud_sql
  create_vpc_connector            = var.create_vpc_connector
  vpc_connector_name              = var.vpc_connector_name
  cloud_sql_db_name               = var.cloud_sql_db_name
  cloud_sql_db_user               = var.cloud_sql_db_user
  cloud_sql_db_password           = var.cloud_sql_db_password
  create_memorystore              = var.create_memorystore
  enable_backend_api_service      = var.enable_backend_api_service
  enable_worker_service           = var.enable_worker_service
  enable_backend_init_job         = var.enable_backend_init_job
  enable_frontend_service         = var.enable_frontend_service
  enable_cloud_tasks_dispatch     = var.enable_cloud_tasks_dispatch
  create_default_scheduler_jobs   = var.create_default_scheduler_jobs
  queue_configs                   = var.queue_configs
  worker_service_base_url         = var.worker_service_base_url
  backend_image                   = var.backend_image
  frontend_image                  = var.frontend_image
  backend_api_command             = var.backend_api_command
  backend_worker_command          = var.backend_worker_command
  backend_init_command            = var.backend_init_command
  backend_api_env                 = var.backend_api_env
  backend_worker_env              = var.backend_worker_env
  backend_init_env                = var.backend_init_env
  frontend_env                    = var.frontend_env
  backend_api_secret_env          = var.backend_api_secret_env
  backend_worker_secret_env       = var.backend_worker_secret_env
  backend_init_secret_env         = var.backend_init_secret_env
  frontend_secret_env             = var.frontend_secret_env
  frontend_custom_domain          = var.frontend_custom_domain
  backend_api_allow_unauthenticated = var.backend_api_allow_unauthenticated
  frontend_allow_unauthenticated    = var.frontend_allow_unauthenticated
  api_service_account_email         = var.api_service_account_email
  worker_service_account_email      = var.worker_service_account_email
  migrator_service_account_email    = var.migrator_service_account_email
  scheduler_service_account_email   = var.scheduler_service_account_email
  frontend_service_account_email    = var.frontend_service_account_email
  backend_api_min_instances         = var.backend_api_min_instances
  backend_vpc_egress                = var.backend_vpc_egress
}

# --- Oura Webhook Renewal (infra-only, no backend code changes) ---

resource "google_cloud_run_v2_job" "oura_webhook_renew" {
  project             = var.project_id
  name                = "${var.name_prefix}-prod-oura-webhook-renew"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = var.api_service_account_email
      timeout         = "120s"
      max_retries     = 2

      containers {
        image   = var.backend_image
        command = ["python3", "-c"]
        args = [<<-PYEOF
import asyncio, os, httpx

API_URL = "https://api.ouraring.com/v2/webhook/subscription"
headers = {"x-client-id": os.environ["OURA_CLIENT_ID"], "x-client-secret": os.environ["OURA_CLIENT_SECRET"]}

async def renew():
    async with httpx.AsyncClient() as client:
        subs = (await client.get(API_URL, headers=headers, timeout=30)).json()
        items = subs if isinstance(subs, list) else []
        print(f"Found {len(items)} subscriptions")
        for sub in items:
            sid = sub.get("id")
            if not sid:
                continue
            r = await client.put(f"{API_URL}/renew/{sid}", headers=headers, timeout=30)
            r.raise_for_status()
            print(f"Renewed {sid}: {r.json()}")
        print(f"Done: {len(items)} renewed")

asyncio.run(renew())
PYEOF
        ]

        env {
          name = "OURA_CLIENT_ID"
          value_source {
            secret_key_ref {
              secret  = "oura_client_id"
              version = "latest"
            }
          }
        }
        env {
          name = "OURA_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = "oura_client_secret"
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "oura_webhook_renew" {
  project     = var.project_id
  region      = var.region
  name        = "${var.name_prefix}-prod-oura-webhook-renew"
  description = "Renew Oura webhook subscriptions weekly (90-day expiry)"
  schedule    = "0 4 * * 1"
  time_zone   = "Etc/UTC"

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.oura_webhook_renew.name}:run"
    http_method = "POST"

    oauth_token {
      service_account_email = var.scheduler_service_account_email
    }
  }
}

# --- Periodic Sync Workaround (sync via API instead of broken internal tasks) ---

resource "google_cloud_run_v2_job" "sync_all_users" {
  project             = var.project_id
  name                = "${var.name_prefix}-prod-sync-all-users"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = var.api_service_account_email
      timeout         = "300s"
      max_retries     = 1

      containers {
        image   = var.backend_image
        command = ["/root_project/.venv/bin/python", "-c"]
        args = [<<-PYEOF
import json, os, urllib.request, urllib.parse

API_URL = os.environ["OW_API_URL"]
API_KEY = os.environ["OW_API_KEY"]

# Login
req = urllib.request.Request(
    f"{API_URL}/api/v1/auth/login",
    data=urllib.parse.urlencode({"username": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
token = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
headers = {"Authorization": f"Bearer {token}", "X-Open-Wearables-API-Key": API_KEY}

# Get all connections
req2 = urllib.request.Request(f"{API_URL}/api/v1/users?page=1&limit=200&sort_by=created_at&sort_order=desc", headers=headers)
try:
    users_data = json.loads(urllib.request.urlopen(req2, timeout=30).read())
    users = users_data if isinstance(users_data, list) else users_data.get("data", users_data.get("items", []))
except Exception as e:
    print(f"Failed to list users: {e}")
    users = []

# Fallback: sync known user directly
if not users:
    users = [{"id": "a864d853-8f77-4b19-a2e0-ac8cdd7cadf0"}]

for user in users:
    uid = user.get("id", user) if isinstance(user, dict) else user
    for provider in ["oura", "strava", "fitbit", "polar"]:
        try:
            req3 = urllib.request.Request(
                f"{API_URL}/api/v1/providers/{provider}/users/{uid}/sync?data_type=all&async=true",
                headers=headers,
                method="POST",
            )
            resp = json.loads(urllib.request.urlopen(req3, timeout=30).read())
            print(f"Sync {provider}/{uid[:8]}: {resp.get('success', '?')}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            print(f"Error {provider}/{uid[:8]}: {e.code}")
        except Exception as e:
            print(f"Error {provider}/{uid[:8]}: {e}")
PYEOF
        ]

        env {
          name  = "OW_API_URL"
          value = "https://ow-api.axl.coach"
        }
        env {
          name  = "OW_API_KEY"
          value = "sk-3091f384be68ce928da29f2f6cc87205"
        }
        env {
          name  = "ADMIN_EMAIL"
          value = "admin@admin.com"
        }
        env {
          name  = "ADMIN_PASSWORD"
          value = "your-secure-password"
        }

        resources {
          limits = {
            cpu    = "1000m"
            memory = "512Mi"
          }
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "sync_all_users_via_api" {
  project     = var.project_id
  region      = var.region
  name        = "${var.name_prefix}-prod-sync-all-users-api"
  description = "Sync all users via OW API (workaround for Cloud Tasks session issue)"
  schedule    = "*/15 * * * *"
  time_zone   = "Etc/UTC"

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.sync_all_users.name}:run"
    http_method = "POST"

    oauth_token {
      service_account_email = var.scheduler_service_account_email
    }
  }
}
