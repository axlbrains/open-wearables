variable "create_network" {
  description = "Whether to create a dedicated VPC network and subnet."
  type        = bool
  default     = true
}

variable "network_name" {
  description = "Optional custom VPC network name."
  type        = string
  default     = null
}

variable "subnetwork_name" {
  description = "Optional custom subnet name."
  type        = string
  default     = null
}

variable "subnet_cidr" {
  description = "CIDR block for the GCP subnet used by Memorystore and the VPC connector."
  type        = string
  default     = "10.10.0.0/24"
}

variable "create_vpc_connector" {
  description = "Whether to create a Serverless VPC Access connector."
  type        = bool
  default     = true
}

variable "vpc_connector_name" {
  description = "Optional custom Serverless VPC Access connector name."
  type        = string
  default     = null
}

variable "vpc_connector_min_instances" {
  description = "Minimum connector instances."
  type        = number
  default     = 2
}

variable "vpc_connector_max_instances" {
  description = "Maximum connector instances."
  type        = number
  default     = 3
}

variable "vpc_connector_machine_type" {
  description = "Machine type for the VPC connector."
  type        = string
  default     = "e2-micro"
}

variable "service_account_project_roles" {
  description = "Project-level IAM roles granted to created service accounts."
  type        = map(list(string))
  default = {
    api = [
      "roles/cloudsql.client",
      "roles/cloudtasks.enqueuer",
      "roles/secretmanager.secretAccessor",
      "roles/storage.objectAdmin",
    ]
    worker = [
      "roles/cloudsql.client",
      "roles/cloudtasks.enqueuer",
      "roles/secretmanager.secretAccessor",
      "roles/storage.objectAdmin",
    ]
    migrator = [
      "roles/cloudsql.client",
      "roles/secretmanager.secretAccessor",
    ]
    scheduler = []
    deployer  = []
  }
}

variable "create_cloud_sql" {
  description = "Whether to provision a Cloud SQL PostgreSQL instance."
  type        = bool
  default     = false
}

variable "cloud_sql_instance_name" {
  description = "Optional custom Cloud SQL instance name."
  type        = string
  default     = null
}

variable "cloud_sql_database_version" {
  description = "Cloud SQL PostgreSQL version."
  type        = string
  default     = "POSTGRES_16"
}

variable "cloud_sql_tier" {
  description = "Cloud SQL instance tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "cloud_sql_availability_type" {
  description = "Cloud SQL availability type."
  type        = string
  default     = "ZONAL"
}

variable "cloud_sql_disk_size_gb" {
  description = "Cloud SQL disk size in GB."
  type        = number
  default     = 20
}

variable "cloud_sql_deletion_protection" {
  description = "Whether to enable deletion protection on Cloud SQL."
  type        = bool
  default     = true
}

variable "cloud_sql_db_name" {
  description = "Application database name."
  type        = string
  default     = "open-wearables"
}

variable "cloud_sql_db_user" {
  description = "Application database user."
  type        = string
  default     = "open_wearables"
}

variable "cloud_sql_db_password" {
  description = "Password for the application database user."
  type        = string
  default     = null
  sensitive   = true
}

variable "create_memorystore" {
  description = "Whether to provision a Memorystore Redis instance."
  type        = bool
  default     = false
}

variable "memorystore_name" {
  description = "Optional custom Memorystore instance name."
  type        = string
  default     = null
}

variable "memorystore_memory_size_gb" {
  description = "Memorystore memory size in GB."
  type        = number
  default     = 1
}

variable "memorystore_tier" {
  description = "Memorystore tier."
  type        = string
  default     = "BASIC"
}

variable "memorystore_version" {
  description = "Memorystore Redis version."
  type        = string
  default     = "REDIS_7_2"
}

variable "enable_backend_api_service" {
  description = "Whether to deploy the public backend API Cloud Run service."
  type        = bool
  default     = false
}

variable "enable_worker_service" {
  description = "Whether to deploy the internal worker Cloud Run service."
  type        = bool
  default     = false
}

variable "enable_backend_init_job" {
  description = "Whether to deploy the backend init/migration Cloud Run Job."
  type        = bool
  default     = false
}

variable "enable_frontend_service" {
  description = "Whether to deploy the frontend Cloud Run service."
  type        = bool
  default     = false
}

variable "enable_cloud_tasks_dispatch" {
  description = "Whether Cloud Run services should dispatch async work through Cloud Tasks."
  type        = bool
  default     = false
}

variable "create_default_scheduler_jobs" {
  description = "Whether to create default Scheduler jobs for periodic worker tasks."
  type        = bool
  default     = false
}

variable "scheduler_time_zone" {
  description = "Time zone for default Scheduler jobs."
  type        = string
  default     = "Etc/UTC"
}

variable "sync_all_users_schedule" {
  description = "Cron schedule for periodic sync fan-out."
  type        = string
  default     = "0 * * * *"
}

variable "finalize_stale_sleeps_schedule" {
  description = "Cron schedule for stale sleep finalization."
  type        = string
  default     = "15 * * * *"
}

variable "gc_stuck_backfills_schedule" {
  description = "Cron schedule for Garmin GC."
  type        = string
  default     = "*/3 * * * *"
}

variable "worker_service_base_url" {
  description = "Stable worker service base URL used by Cloud Tasks dispatch."
  type        = string
  default     = null
}

variable "api_service_account_email" {
  description = "Optional existing service account email for the API service."
  type        = string
  default     = null
}

variable "worker_service_account_email" {
  description = "Optional existing service account email for the worker service."
  type        = string
  default     = null
}

variable "migrator_service_account_email" {
  description = "Optional existing service account email for the migrator job."
  type        = string
  default     = null
}

variable "frontend_service_account_email" {
  description = "Optional existing service account email for the frontend service."
  type        = string
  default     = null
}

variable "scheduler_service_account_email" {
  description = "Optional existing service account email for Scheduler OIDC invocations."
  type        = string
  default     = null
}

variable "task_dispatcher_service_account_email" {
  description = "Optional service account email used by Cloud Tasks OIDC callbacks."
  type        = string
  default     = null
}

variable "backend_image" {
  description = "Backend container image for Cloud Run services and jobs."
  type        = string
  default     = null
}

variable "frontend_image" {
  description = "Frontend container image for Cloud Run."
  type        = string
  default     = null
}

variable "backend_api_service_name" {
  description = "Optional custom backend API Cloud Run service name."
  type        = string
  default     = null
}

variable "backend_worker_service_name" {
  description = "Optional custom worker Cloud Run service name."
  type        = string
  default     = null
}

variable "backend_init_job_name" {
  description = "Optional custom backend init job name."
  type        = string
  default     = null
}

variable "frontend_service_name" {
  description = "Optional custom frontend Cloud Run service name."
  type        = string
  default     = null
}

variable "backend_container_port" {
  description = "Backend container port."
  type        = number
  default     = 8000
}

variable "frontend_container_port" {
  description = "Frontend container port."
  type        = number
  default     = 3000
}

variable "backend_api_command" {
  description = "Command for the backend API service container."
  type        = list(string)
  default     = ["scripts/start/cloud-run-api.sh"]
}

variable "backend_api_args" {
  description = "Args for the backend API service container."
  type        = list(string)
  default     = []
}

variable "backend_worker_command" {
  description = "Command for the backend worker service container."
  type        = list(string)
  default     = ["scripts/start/cloud-run-api.sh"]
}

variable "backend_worker_args" {
  description = "Args for the backend worker service container."
  type        = list(string)
  default     = []
}

variable "backend_init_command" {
  description = "Command for the backend init job container."
  type        = list(string)
  default     = ["scripts/start/cloud-run-init.sh"]
}

variable "backend_init_args" {
  description = "Args for the backend init job container."
  type        = list(string)
  default     = []
}

variable "frontend_command" {
  description = "Optional command for the frontend container."
  type        = list(string)
  default     = []
}

variable "frontend_args" {
  description = "Optional args for the frontend container."
  type        = list(string)
  default     = []
}

variable "backend_api_env" {
  description = "Plaintext env vars for the backend API service."
  type        = map(string)
  default     = {}
}

variable "backend_worker_env" {
  description = "Plaintext env vars for the backend worker service."
  type        = map(string)
  default     = {}
}

variable "backend_init_env" {
  description = "Plaintext env vars for the backend init job."
  type        = map(string)
  default     = {}
}

variable "frontend_env" {
  description = "Plaintext env vars for the frontend service."
  type        = map(string)
  default     = {}
}

variable "backend_api_secret_env" {
  description = "Secret Manager env vars for the backend API service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "backend_worker_secret_env" {
  description = "Secret Manager env vars for the backend worker service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "backend_init_secret_env" {
  description = "Secret Manager env vars for the backend init job."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "frontend_secret_env" {
  description = "Secret Manager env vars for the frontend service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "backend_api_resource_limits" {
  description = "Resource limits for the backend API service."
  type        = map(string)
  default = {
    cpu    = "1"
    memory = "512Mi"
  }
}

variable "backend_worker_resource_limits" {
  description = "Resource limits for the backend worker service."
  type        = map(string)
  default = {
    cpu    = "1"
    memory = "1Gi"
  }
}

variable "backend_init_resource_limits" {
  description = "Resource limits for the backend init job."
  type        = map(string)
  default = {
    cpu    = "1"
    memory = "512Mi"
  }
}

variable "frontend_resource_limits" {
  description = "Resource limits for the frontend service."
  type        = map(string)
  default = {
    cpu    = "1"
    memory = "512Mi"
  }
}

variable "backend_api_min_instances" {
  description = "Minimum backend API instances."
  type        = number
  default     = 0
}

variable "backend_api_max_instances" {
  description = "Maximum backend API instances."
  type        = number
  default     = 5
}

variable "backend_worker_min_instances" {
  description = "Minimum worker instances."
  type        = number
  default     = 0
}

variable "backend_worker_max_instances" {
  description = "Maximum worker instances."
  type        = number
  default     = 5
}

variable "frontend_min_instances" {
  description = "Minimum frontend instances."
  type        = number
  default     = 0
}

variable "frontend_max_instances" {
  description = "Maximum frontend instances."
  type        = number
  default     = 3
}

variable "backend_api_timeout_seconds" {
  description = "Backend API request timeout in seconds."
  type        = number
  default     = 300
}

variable "backend_worker_timeout_seconds" {
  description = "Backend worker request timeout in seconds."
  type        = number
  default     = 3600
}

variable "backend_init_timeout_seconds" {
  description = "Backend init job timeout in seconds."
  type        = number
  default     = 3600
}

variable "frontend_timeout_seconds" {
  description = "Frontend request timeout in seconds."
  type        = number
  default     = 300
}

variable "backend_api_concurrency" {
  description = "Backend API request concurrency."
  type        = number
  default     = 80
}

variable "backend_worker_concurrency" {
  description = "Backend worker request concurrency."
  type        = number
  default     = 10
}

variable "frontend_concurrency" {
  description = "Frontend request concurrency."
  type        = number
  default     = 80
}

variable "backend_api_ingress" {
  description = "Ingress mode for the backend API service."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "backend_worker_ingress" {
  description = "Ingress mode for the worker service."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "frontend_ingress" {
  description = "Ingress mode for the frontend service."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "backend_api_allow_unauthenticated" {
  description = "Whether to allow unauthenticated access to the backend API service."
  type        = bool
  default     = true
}

variable "frontend_allow_unauthenticated" {
  description = "Whether to allow unauthenticated access to the frontend service."
  type        = bool
  default     = true
}

variable "backend_vpc_egress" {
  description = "VPC egress mode for backend services."
  type        = string
  default     = "PRIVATE_RANGES_ONLY"
}
