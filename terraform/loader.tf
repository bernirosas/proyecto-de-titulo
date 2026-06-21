resource "google_cloud_run_v2_job" "loader" {
  name     = "maqui-loader"
  location = var.region

  deletion_protection = false

  template {
    template {
      timeout     = "3600s"
      max_retries = 1

      vpc_access {
        connector = google_vpc_access_connector.maqui.id
        egress    = "PRIVATE_RANGES_ONLY"
      }

      volumes {
        name = "artifacts"
        gcs {
          bucket    = google_storage_bucket.artifacts.name
          read_only = true
        }
      }

      containers {
        image   = local.image_url
        command = ["sh", "-c"]
        args    = ["python scripts/create_index.py --force && python scripts/ingest_with_vectors.py --pass all"]

        resources {
          limits = {
            cpu    = "2"
            memory = "8Gi"
          }
        }

        volume_mounts {
          name       = "artifacts"
          mount_path = "/app/gcs"
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
          name  = "VECTORS_DIR"
          value = "/app/gcs/vectors"
        }
      }
    }
  }

  depends_on = [google_storage_bucket_iam_member.reader]
}
