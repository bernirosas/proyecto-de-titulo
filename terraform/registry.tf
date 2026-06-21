resource "google_artifact_registry_repository" "maqui" {
  location      = var.region
  repository_id = var.repo
  format        = "DOCKER"
  description   = "Imagenes sparse_eval Maqui"

  depends_on = [google_project_service.apis]
}
