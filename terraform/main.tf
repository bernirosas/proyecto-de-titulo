terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  apis = [
    "run.googleapis.com",
    "compute.googleapis.com",
    "artifactregistry.googleapis.com",
    "vpcaccess.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "iap.googleapis.com",
  ]

  image_url  = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repo}/sparse-eval:${var.image_tag}"
  bucket     = "${var.project_id}-maqui-artifacts"
  compute_sa = "${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "this" {}
