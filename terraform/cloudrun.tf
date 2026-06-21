resource "google_cloud_run_v2_service" "api" {
  name     = "maqui-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    scaling {
      min_instance_count = var.cr_min_instances
      max_instance_count = var.cr_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.maqui.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    max_instance_request_concurrency = 8
    timeout                          = "300s"

    containers {
      image = local.image_url

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cr_cpu
          memory = var.cr_memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "OPENSEARCH_HOST"
        value = google_compute_instance.vm.network_interface[0].network_ip
      }
      env {
        name  = "OPENSEARCH_PORT"
        value = "9200"
      }
      env {
        name  = "QDRANT_URL"
        value = "http://${google_compute_instance.vm.network_interface[0].network_ip}:6333"
      }
      env {
        name  = "QDRANT_COLLECTION"
        value = "maqui"
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.gemini,
    google_secret_manager_secret_iam_member.gemini_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
