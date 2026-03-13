variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Primary region for regional resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name, such as dev or prod."
  type        = string
}

variable "name_prefix" {
  description = "Prefix used for resource naming."
  type        = string
  default     = "open-wearables"
}

variable "labels" {
  description = "Common labels applied to supported resources."
  type        = map(string)
  default     = {}
}

variable "enable_apis" {
  description = "Whether Terraform should enable required Google APIs."
  type        = bool
  default     = true
}

variable "activate_apis" {
  description = "Google APIs required by the GCP overlay."
  type        = list(string)
  default = [
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "vpcaccess.googleapis.com",
  ]
}

variable "create_artifact_registry" {
  description = "Whether to create the Docker Artifact Registry repository."
  type        = bool
  default     = true
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository ID."
  type        = string
  default     = "open-wearables"
}

variable "artifact_registry_description" {
  description = "Artifact Registry repository description."
  type        = string
  default     = "Container images for Open Wearables deployments"
}

variable "create_service_accounts" {
  description = "Whether to create dedicated service accounts."
  type        = bool
  default     = true
}

variable "service_accounts" {
  description = "Service accounts used by the deployment."
  type = map(object({
    display_name = string
    description  = string
  }))
  default = {
    api = {
      display_name = "Open Wearables API"
      description  = "Runs the public Cloud Run API service"
    }
    worker = {
      display_name = "Open Wearables Worker"
      description  = "Runs internal async HTTP handlers on Cloud Run"
    }
    migrator = {
      display_name = "Open Wearables Migrator"
      description  = "Runs Cloud Run jobs for migrations and initialization"
    }
    scheduler = {
      display_name = "Open Wearables Scheduler"
      description  = "Invokes Cloud Scheduler HTTP targets"
    }
    deployer = {
      display_name = "Open Wearables Deployer"
      description  = "Deploys images and updates Cloud Run services"
    }
  }
}

variable "queue_configs" {
  description = "Cloud Tasks queues used by the async migration path."
  type = map(object({
    max_dispatches_per_second = number
    max_concurrent_dispatches = number
    max_attempts              = number
    min_backoff               = string
    max_backoff               = string
  }))
  default = {
    default = {
      max_dispatches_per_second = 5
      max_concurrent_dispatches = 20
      max_attempts              = 10
      min_backoff               = "5s"
      max_backoff               = "300s"
    }
    sdk_sync = {
      max_dispatches_per_second = 10
      max_concurrent_dispatches = 50
      max_attempts              = 8
      min_backoff               = "5s"
      max_backoff               = "120s"
    }
    garmin_backfill = {
      max_dispatches_per_second = 2
      max_concurrent_dispatches = 5
      max_attempts              = 20
      min_backoff               = "15s"
      max_backoff               = "600s"
    }
  }
}

variable "create_secrets" {
  description = "Whether to create Secret Manager secret placeholders."
  type        = bool
  default     = false
}

variable "secret_names" {
  description = "Secret Manager secret IDs to create without versions."
  type        = list(string)
  default     = []
}

variable "github_owner" {
  description = "GitHub repository owner for Cloud Build triggers."
  type        = string
  default     = ""
}

variable "github_repository_name" {
  description = "GitHub repository name for Cloud Build triggers."
  type        = string
  default     = ""
}

variable "branch_pattern" {
  description = "Branch pattern to trigger Cloud Build (e.g. ^main$)."
  type        = string
  default     = "^main$"
}

variable "scheduler_jobs" {
  description = "Cloud Scheduler jobs for periodic task replacements."
  type = map(object({
    description                = string
    schedule                   = string
    time_zone                  = optional(string, "Etc/UTC")
    target_url                 = string
    oidc_service_account_email = string
    audience                   = optional(string)
    http_method                = optional(string, "POST")
    headers                    = optional(map(string), {})
    body                       = optional(string)
  }))
  default = {}
}
