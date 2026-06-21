resource "google_compute_disk" "data" {
  name = "maqui-data"
  type = "pd-ssd"
  zone = var.zone
  size = var.data_disk_gb

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_instance" "vm" {
  name         = "maqui-search"
  machine_type = var.vm_machine_type
  zone         = var.zone
  tags         = ["maqui-search"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 20
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "maqui-data"
  }

  network_interface {
    network = data.google_compute_network.default.name
    access_config {}
  }

  service_account {
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/scripts/vm-startup.sh", {
    bucket = local.bucket
  })

  lifecycle {
    ignore_changes = [metadata_startup_script]
  }

  depends_on = [google_project_service.apis]
}
