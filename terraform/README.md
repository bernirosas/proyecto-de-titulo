# Infraestructura (Terraform)

Despliegue del backend `sparse_eval` en Google Cloud con una arquitectura híbrida:

- **App** (FastAPI + frontend) en **Cloud Run**.
- **Motores de búsqueda** (OpenSearch + Qdrant) en una **VM de Compute Engine** con disco persistente.
- Comunicación **privada** entre ambos vía Serverless VPC Access; la app es la única superficie pública.

El estado de Terraform es local. La gestión de la imagen (build) y la carga de datos
quedan fuera de Terraform y se ejecutan como pasos puntuales (secciones 2 y 4).

## Recursos gestionados

- Habilitación de APIs, Artifact Registry y Secret Manager.
- VPC connector y reglas de firewall (motores accesibles solo desde el connector; SSH solo vía IAP).
- VM `e2-standard-4` con disco de datos persistente (`prevent_destroy`) que se auto-siembra Qdrant desde GCS.
- Bucket de artefactos (`qdrant_storage/` + `vectors/`).
- Cloud Run Job `maqui-loader` para la ingesta de OpenSearch.
- Servicio Cloud Run `maqui-api` (4 vCPU / 8 GiB, `min-instances=0`).

## Requisitos

- Terraform >= 1.5 y `gcloud` autenticado.
- Proyecto GCP con facturación habilitada.

## Despliegue

### 1. Configuración

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # completar project_id y gemini_key
terraform init
terraform apply -target=google_project_service.apis -target=google_artifact_registry_repository.maqui -target=google_storage_bucket.artifacts
```

### 2. Imagen de la app

```bash
gcloud builds submit .. --tag "$(terraform output -raw image_url)" --timeout=3600s
```

### 3. Resto de la infraestructura

```bash
terraform apply
```

### 4. Carga de datos (una sola vez)

```bash
BUCKET=$(terraform output -raw artifacts_bucket)
gcloud storage rsync -r ../../qdrant_storage "gs://$BUCKET/qdrant_storage"
gcloud storage rsync -r ../vectors           "gs://$BUCKET/vectors"
gcloud run jobs execute maqui-loader --region=southamerica-west1 --wait
```

La VM siembra Qdrant en su primer arranque y el Job ingesta OpenSearch. Ambos datos
persisten en el disco, por lo que la carga se realiza una única vez.

### 5. Verificación

```bash
curl -s "$(terraform output -raw cloud_run_url)/healthz"
```

## Operación (modo demo)

Para reducir costos entre demos, destruir solo los recursos de cómputo conservando los datos:

```bash
terraform destroy \
  -target=google_cloud_run_v2_service.api \
  -target=google_compute_instance.vm \
  -target=google_vpc_access_connector.maqui
```

Un `terraform apply` posterior recrea la VM y re-monta el disco existente sin reingestar.

## Notas

- `terraform.tfvars` y el estado contienen datos sensibles y están excluidos del control de versiones.
- El disco de datos tiene `prevent_destroy`; un `terraform destroy` completo falla por diseño.
  Para eliminarlo, quitar el bloque `lifecycle` o borrarlo manualmente.
