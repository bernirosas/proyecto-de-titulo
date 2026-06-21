#!/usr/bin/env bash
# Itera sobre todos los pools en scripts/benchmark/pools/ y llama
# judge_pool.py para cada uno. judge_pool.py es incremental por default
# (preserva judgments válidos existentes y solo paga llamadas a Gemini
# por los chunks nuevos o los que tenían grade=-1), así que correr este
# wrapper varias veces es seguro e idempotente.
#
# Uso:
#   export GEMINI_API_KEY="..."
#   bash scripts/benchmark/judge_all.sh

set -u

MODEL="gemini-2.5-flash-lite"

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "[x] GEMINI_API_KEY no exportada"
    exit 1
fi

for pool in scripts/benchmark/pools/q*.json; do
    [ -f "$pool" ] || continue
    n=$(basename "$pool" .json)
    echo ""
    echo "=========================================="
    echo "  Judge: $n"
    echo "=========================================="
    docker compose run --rm -e GEMINI_API_KEY app \
        python scripts/benchmark/judge_pool.py \
            --pool-file "$pool" \
            --output-dir scripts/benchmark/judgments \
            --model "$MODEL"
    if [ $? -ne 0 ]; then
        echo "[x] falló $n — abortando para no quemar cuota en las siguientes."
        break
    fi
done

echo ""
echo "=========================================="
echo "  Judge finalizado"
echo "=========================================="
