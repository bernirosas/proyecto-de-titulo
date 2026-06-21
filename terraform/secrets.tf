resource "google_secret_manager_secret" "gemini" {
  secret_id = "gemini-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gemini" {
  secret      = google_secret_manager_secret.gemini.id
  secret_data = var.gemini_key
}

resource "google_secret_manager_secret_iam_member" "gemini_accessor" {
  secret_id = google_secret_manager_secret.gemini.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.compute_sa}"
}
