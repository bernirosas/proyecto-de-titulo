data "google_compute_network" "default" {
  name = "default"
}

resource "google_vpc_access_connector" "maqui" {
  name          = "maqui-connector"
  region        = var.region
  network       = data.google_compute_network.default.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3

  depends_on = [google_project_service.apis]
}

resource "google_compute_firewall" "allow_search_from_connector" {
  name      = "maqui-allow-search"
  network   = data.google_compute_network.default.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["9200", "6333", "6334"]
  }

  source_ranges = ["10.8.0.0/28"]
  target_tags   = ["maqui-search"]
}

resource "google_compute_firewall" "allow_ssh_iap" {
  name      = "maqui-allow-ssh-iap"
  network   = data.google_compute_network.default.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["maqui-search"]
}
