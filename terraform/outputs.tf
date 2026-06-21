output "cloud_run_url" {
  value       = google_cloud_run_v2_service.api.uri
  description = "URL publica de la app."
}

output "vm_internal_ip" {
  value       = google_compute_instance.vm.network_interface[0].network_ip
  description = "IP privada de la VM."
}

output "vm_external_ip" {
  value       = google_compute_instance.vm.network_interface[0].access_config[0].nat_ip
  description = "IP externa efimera de la VM."
}

output "image_url" {
  value       = local.image_url
  description = "Imagen que Cloud Run espera en Artifact Registry."
}

output "artifacts_bucket" {
  value       = google_storage_bucket.artifacts.name
  description = "Bucket de artefactos (qdrant_storage/ + vectors/)."
}
