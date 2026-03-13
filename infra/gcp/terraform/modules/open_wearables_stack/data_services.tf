locals {
  cloud_sql_instance_name_resolved = coalesce(var.cloud_sql_instance_name, "${local.resource_prefix}-db")
  memorystore_name_resolved        = coalesce(var.memorystore_name, "${local.resource_prefix}-redis")
}

resource "google_sql_database_instance" "main" {
  count = var.create_cloud_sql ? 1 : 0

  project             = var.project_id
  name                = local.cloud_sql_instance_name_resolved
  region              = var.region
  database_version    = var.cloud_sql_database_version
  deletion_protection = var.cloud_sql_deletion_protection

  settings {
    tier              = var.cloud_sql_tier
    availability_type = var.cloud_sql_availability_type
    disk_size         = var.cloud_sql_disk_size_gb
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled = true
    }

    backup_configuration {
      enabled = true
    }
  }

  lifecycle {
    precondition {
      condition     = var.cloud_sql_db_password != null
      error_message = "cloud_sql_db_password must be set when create_cloud_sql is true."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "app" {
  count = var.create_cloud_sql ? 1 : 0

  project  = var.project_id
  name     = var.cloud_sql_db_name
  instance = google_sql_database_instance.main[0].name
}

resource "google_sql_user" "app" {
  count = var.create_cloud_sql ? 1 : 0

  project  = var.project_id
  instance = google_sql_database_instance.main[0].name
  name     = var.cloud_sql_db_user
  password = var.cloud_sql_db_password
}

resource "google_redis_instance" "main" {
  count = var.create_memorystore ? 1 : 0

  project            = var.project_id
  region             = var.region
  name               = local.memorystore_name_resolved
  tier               = var.memorystore_tier
  memory_size_gb     = var.memorystore_memory_size_gb
  redis_version      = var.memorystore_version
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  authorized_network = google_compute_network.main[0].id

  lifecycle {
    precondition {
      condition     = var.create_network
      error_message = "create_network must be true when create_memorystore is true."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "task_payloads" {
  count = var.enable_cloud_tasks_dispatch ? 1 : 0

  project                     = var.project_id
  name                        = "${local.resource_prefix}-task-payloads"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 7 # Delete objects older than 7 days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

