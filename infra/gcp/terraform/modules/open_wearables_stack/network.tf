locals {
  network_name_resolved    = coalesce(var.network_name, "${local.resource_prefix}-network")
  subnetwork_name_resolved = coalesce(var.subnetwork_name, "${local.resource_prefix}-subnet")
  vpc_connector_name_resolved = coalesce(
    var.vpc_connector_name,
    "${local.resource_prefix}-connector",
  )
}

resource "google_compute_network" "main" {
  count = var.create_network ? 1 : 0

  project                 = var.project_id
  name                    = local.network_name_resolved
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "main" {
  count = var.create_network ? 1 : 0

  project                  = var.project_id
  name                     = local.subnetwork_name_resolved
  region                   = var.region
  ip_cidr_range            = var.subnet_cidr
  network                  = google_compute_network.main[0].id
  private_ip_google_access = true
}

resource "google_vpc_access_connector" "main" {
  count = var.create_vpc_connector && var.create_network ? 1 : 0

  project       = var.project_id
  name          = local.vpc_connector_name_resolved
  region        = var.region
  machine_type  = var.vpc_connector_machine_type
  min_instances = var.vpc_connector_min_instances
  max_instances = var.vpc_connector_max_instances

  subnet {
    name = google_compute_subnetwork.main[0].name
  }

  depends_on = [google_project_service.required]
}
