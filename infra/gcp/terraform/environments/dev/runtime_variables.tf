variable "create_network" {
  description = "Whether to create a dedicated VPC network and subnet."
  type        = bool
  default     = true
}

variable "create_cloud_sql" {
  description = "Whether to provision Cloud SQL."
  type        = bool
  default     = false
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
  description = "Application database password."
  type        = string
  default     = null
  sensitive   = true
}

variable "create_memorystore" {
  description = "Whether to provision Memorystore."
  type        = bool
  default     = false
}

variable "enable_backend_api_service" {
  description = "Whether to deploy the backend API service."
  type        = bool
  default     = false
}

variable "enable_worker_service" {
  description = "Whether to deploy the worker service."
  type        = bool
  default     = false
}

variable "enable_backend_init_job" {
  description = "Whether to deploy the backend init job."
  type        = bool
  default     = false
}

variable "enable_frontend_service" {
  description = "Whether to deploy the frontend service."
  type        = bool
  default     = false
}

variable "enable_cloud_tasks_dispatch" {
  description = "Whether to enable Cloud Tasks dispatch in runtime env."
  type        = bool
  default     = false
}

variable "create_default_scheduler_jobs" {
  description = "Whether to create default Scheduler jobs."
  type        = bool
  default     = false
}

variable "worker_service_base_url" {
  description = "Stable worker service base URL used by Cloud Tasks dispatch."
  type        = string
  default     = null
}

variable "backend_image" {
  description = "Backend image reference."
  type        = string
  default     = null
}

variable "frontend_image" {
  description = "Frontend image reference."
  type        = string
  default     = null
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
  description = "Secret env vars for the backend API service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "backend_worker_secret_env" {
  description = "Secret env vars for the backend worker service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "backend_init_secret_env" {
  description = "Secret env vars for the backend init job."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}

variable "frontend_secret_env" {
  description = "Secret env vars for the frontend service."
  type = map(object({
    secret  = string
    version = optional(string, "latest")
  }))
  default = {}
}
