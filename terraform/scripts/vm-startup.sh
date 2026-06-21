#!/bin/bash
set -euo pipefail

DATA=/mnt/disks/data
DISK=/dev/disk/by-id/google-maqui-data
BUCKET="${bucket}"

if ! blkid "$DISK" >/dev/null 2>&1; then
  mkfs.ext4 -F "$DISK"
fi

mkdir -p "$DATA"
mountpoint -q "$DATA" || mount "$DISK" "$DATA"
mkdir -p "$DATA/opensearch" "$DATA/qdrant"
chmod -R 777 "$DATA"

if [ -z "$(ls -A "$DATA/qdrant" 2>/dev/null)" ]; then
  docker run --rm --network host -v "$DATA:/data" \
    gcr.io/google.com/cloudsdktool/google-cloud-cli:slim \
    gcloud storage rsync -r "gs://$BUCKET/qdrant_storage" /data/qdrant
  chmod -R 777 "$DATA/qdrant"
fi

sysctl -w vm.max_map_count=262144 || true

docker rm -f opensearch >/dev/null 2>&1 || true
docker run -d --name opensearch --restart unless-stopped \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e bootstrap.memory_lock=true \
  -e OPENSEARCH_JAVA_OPTS="-Xms1g -Xmx1g" \
  -e DISABLE_SECURITY_PLUGIN=true \
  -e DISABLE_INSTALL_DEMO_CONFIG=true \
  --ulimit memlock=-1:-1 \
  --ulimit nofile=65536:65536 \
  -v "$DATA/opensearch:/usr/share/opensearch/data" \
  opensearchproject/opensearch:2.15.0

docker rm -f qdrant >/dev/null 2>&1 || true
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v "$DATA/qdrant:/qdrant/storage" \
  qdrant/qdrant:v1.15.4
