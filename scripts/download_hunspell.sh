#!/usr/bin/env bash
# Descarga los diccionarios hunspell de español (locale es_ES) y los deja en
# hunspell/es_ES/ del proyecto. OpenSearch los carga en arranque desde
# /usr/share/opensearch/config/hunspell/es_ES/ vía el bind-mount declarado en
# docker-compose.yml.
#
# Uso:
#   bash scripts/download_hunspell.sh
#
# Después de correrlo:
#   docker compose restart opensearch          # carga los diccionarios
#   docker compose run --rm app python scripts/create_index.py --force
#   docker compose run --rm app python scripts/ingest.py
set -euo pipefail

DEST="$(dirname "$0")/../hunspell/es_ES"
mkdir -p "$DEST"

# Mirror estable de diccionarios hunspell. Los archivos vienen como
# index.aff e index.dic; OpenSearch espera <locale>.aff y <locale>.dic.
BASE="https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/es"

echo "Bajando es_ES.aff..."
curl -fL "$BASE/index.aff" -o "$DEST/es_ES.aff"

echo "Bajando es_ES.dic..."
curl -fL "$BASE/index.dic" -o "$DEST/es_ES.dic"

echo
echo "OK. Diccionarios en $DEST"
ls -lh "$DEST"
