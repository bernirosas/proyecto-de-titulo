variable "project_id" {
  type        = string
  description = "ID del proyecto GCP."
}

variable "region" {
  type        = string
  default     = "southamerica-west1"
  description = "Región de despliegue."
}

variable "zone" {
  type        = string
  default     = "southamerica-west1-a"
  description = "Zona de la VM."
}

variable "repo" {
  type        = string
  default     = "maqui"
  description = "Nombre del repositorio de Artifact Registry."
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Tag de la imagen de la app a desplegar en Cloud Run."
}

variable "gemini_key" {
  type        = string
  sensitive   = true
  description = "API key de Gemini para el embedding de queries en vivo."
}

variable "vm_machine_type" {
  type        = string
  default     = "e2-standard-4"
  description = "Tipo de máquina de la VM con OpenSearch + Qdrant."
}

variable "data_disk_gb" {
  type        = number
  default     = 30
  description = "Tamaño del disco persistente de datos."
}

variable "cr_min_instances" {
  type        = number
  default     = 0
  description = "Instancias mínimas de Cloud Run (0 = solo demos)."
}

variable "cr_max_instances" {
  type    = number
  default = 3
}

variable "cr_cpu" {
  type    = string
  default = "4"
}

variable "cr_memory" {
  type    = string
  default = "8Gi"
}
