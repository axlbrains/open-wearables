locals {
  service_account_role_pairs = flatten([
    for account_key, roles in var.service_account_project_roles : [
      for role in roles : {
        key         = "${account_key}-${replace(role, "/", "_")}"
        account_key = account_key
        role        = role
      }
    ]
  ])
}

resource "google_project_iam_member" "service_account_roles" {
  for_each = var.create_service_accounts ? { for pair in local.service_account_role_pairs : pair.key => pair } : {}

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.accounts[each.value.account_key].email}"

  # cloudsql.client is project-wide by default, which let each stack's SAs open
  # every other instance in the project (test could reach prod's DB). Pin it to
  # this stack's own instance.
  dynamic "condition" {
    for_each = each.value.role == "roles/cloudsql.client" && local.cloud_sql_instance_name != null ? [1] : []
    content {
      title       = "only-${local.cloud_sql_instance_name}"
      description = "Cloud SQL access limited to this stack's instance"
      expression  = "resource.name == \"projects/${var.project_id}/instances/${local.cloud_sql_instance_name}\" && resource.service == \"sqladmin.googleapis.com\""
    }
  }

  # Adding or changing the condition forces replacement; grant the new binding
  # before revoking the old one so the services never lose DB access.
  lifecycle {
    create_before_destroy = true
  }
}
