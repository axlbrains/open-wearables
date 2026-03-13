variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Primary deployment region."
  type        = string
}

variable "name_prefix" {
  description = "Prefix used for resource names."
  type        = string
  default     = "open-wearables"
}

variable "labels" {
  description = "Common labels applied to supported resources."
  type        = map(string)
  default     = {}
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository ID."
  type        = string
  default     = "open-wearables-prod"
}

variable "create_secrets" {
  description = "Whether to create Secret Manager secret placeholders."
  type        = bool
  default     = false
}

variable "secret_names" {
  description = "Secret IDs to create when create_secrets is true."
  type        = list(string)
  default     = []
}

variable "scheduler_jobs" {
  description = "Cloud Scheduler jobs for periodic task execution."
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
