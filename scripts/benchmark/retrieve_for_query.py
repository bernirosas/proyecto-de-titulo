"""Ejecuta una query contra las 16 técnicas y produce el pool para juzgar.

Por cada query, levanta el top-k de:

  - **8 técnicas esparsas** (P1/P2/P3 × BM25/TF-IDF + SPLADE +
    `baseline_qdrant_bm25`), nombradas tal cual en el catálogo.
  - **8 combos híbridos RRF** (`rrf_<sparse>`): cada uno fusiona el
    ranking denso (Gemini en Qdrant) con uno de los 8 sparse vía
    Reciprocal Rank Fusion (Cormack, Clarke & Buettcher 2009).
    Sólo se ejecutan si la query tiene embedding denso pre-computado
    en `queries_dense/queries_dense.json`; si no, se omiten silenciosamente.

Une los chunk_uuid de los 16 rankings en un pool único sin repeticiones y
los aleatoriza con seed fija para evitar sesgos de orden cuando el juez
procese los chunks.

Doble salida:

1. **Archivo JSON** en `pools/{query_id}.json` — el pool hidratado con el
   contenido de cada chunk, listo para que el juez (LLM) lo procese.
2. **Índice OpenSearch** `retrieval_results` — una fila por (query_id,
   technique_name) con el top-k crudo. Sirve de evidencia auditable de qué
   retornó cada técnica y se usará al computar Recall@k / MRR / NDCG
   uniéndolo con el índice `ground_truth`. Es idempotente: re-correr la
   misma query sobrescribe la fila correspondiente.

Las 8 sparse incluyen las 7 propias (P1/P2/P3 × BM25/TF-IDF + SPLADE)
más `baseline_qdrant_bm25`, que importa los vectores que el cliente ya
tiene en su instancia Qdrant (fastembed `Qdrant/bm25` con Snowball English
y MurmurHash3). Aunque conceptualmente cercano a `p3_bm25`, su
implementación y su pipeline de upstream son distintos.

Uso:
    python scripts/benchmark/retrieve_for_query.py \\
        --query-file scripts/benchmark/queries/q001_prescripcion_cobro.json \\
        --output-dir scripts/benchmark/pools \\
        --size 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Este script vive en scripts/benchmark/ pero importa `from src import ...`
# (clients, config, search). Ejecutado como
# `python scripts/benchmark/retrieve_for_query.py`, Python solo agrega
# scripts/benchmark/ al sys.path, no la raiz del repo, y `import src` falla
# con ModuleNotFoundError. `parents[2]` sube desde
# .../scripts/benchmark/retrieve_for_query.py hasta la raiz del repo;
# insertarla en la posicion 0 le da prioridad y permite que los imports
# absolutos resuelvan.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensearchpy.helpers import bulk
from src import clients, config, dense_qdrant, search

# Prefijo que distingue rankings híbridos en los pools. `consolidate_evaluations.py`
# usa este prefijo para separar el reporte sparse del reporte híbrido.
HYBRID_PREFIX = "rrf_"

# Campos del chunk que viajan al juez (LLM). content truncado a 3000
# caracteres porque la mayoría de los chunks son más cortos y Gemini
# cobra/cuenta por tokens.
_HYDRATE_FIELDS = [
    "chunk_uuid",
    "chunk_id",
    "document_id",
    "name",
    "source",
    "source_type",
    "url",
    "content",
]


# Mapping del índice retrieval_results. Una fila por (query_id, technique_name).
# El _id se construye como "<query_id>::<technique_name>" para que re-correr la
# misma query sobreescriba en lugar de duplicar.
_RETRIEVAL_RESULTS_MAPPING = {
    "settings": {
        "index": {"number_of_shards": 1, "number_of_replicas": 0},
    },
    "mappings": {
        "properties": {
            "run_id": {"type": "keyword"},
            "query_id": {"type": "keyword"},
            "query_text": {"type": "text"},
            "technique_name": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "size": {"type": "integer"},
            "latency_ms": {"type": "float"},
            "hits": {
                # nested permite buscar por hit individual sin perder la
                # asociación con su rank y score.
                "type": "nested",
                "properties": {
                    "chunk_uuid": {"type": "keyword"},
                    "score": {"type": "float"},
                    "rank": {"type": "integer"},
                },
            },
        }
    },
}


def retrieve_all_sparse(query_text: str, size: int) -> tuple[dict, dict]:
    """Top-k por cada técnica esparsa de config.TECHNIQUES.

    Devuelve (rankings, latencies): latencies[method] es la latencia en
    ms de esa busqueda (search.search la mide de extremo a extremo).
    Queda como evidencia comparable entre tecnicas.

    Excluye `hybrid_rrf` adrede — esa técnica es compositiva y se
    materializa una vez por sparse partner en `retrieve_all_hybrid()`.
    """
    rankings: dict = {}
    latencies: dict = {}
    for method in config.TECHNIQUES:
        if method == "hybrid_rrf":
            continue
        result = search.search(query=query_text, method=method, size=size)
        rankings[method] = [
            {"chunk_uuid": h["chunk_uuid"], "score": h["score"], "rank": i + 1}
            for i, h in enumerate(result["hits"])
        ]
        latencies[method] = result.get("latency_ms")
    return rankings, latencies


def retrieve_all_hybrid(query_text: str, query_id: str, size: int) -> tuple[dict, dict]:
    """Top-k por cada combo híbrido RRF (dense + sparse partner).

    Por cada uno de los 8 sparse partners declarados en
    `config.HYBRID_SPARSE_VARIANTS`, ejecuta `hybrid_rrf` y devuelve el
    ranking con clave `rrf_<sparse_partner>`. Si la query no tiene
    embedding denso pre-computado (`dense_qdrant.get_query_vector` levanta
    `ValueError`), se omite silenciosamente toda la familia híbrida
    devolviendo dicts vacíos — eso permite que el script siga corriendo
    para queries del pipeline antiguo sin romper.

    El esquema de claves `rrf_<sparse>` (en vez de `hybrid+sparse` u
    otro separador) garantiza que el prefijo `rrf_` sea un discriminador
    estable para que `consolidate_evaluations.py` separe los reportes
    sparse y híbrido. Se evita el `+` porque rompe nombres de archivo en
    algunos pipelines downstream (p. ej. shell scripts).
    """
    # Probe rápido: si no hay vector denso para esta query, no tiene
    # sentido recorrer los 8 partners (cada uno volvería a fallar igual).
    try:
        dense_qdrant.get_query_vector(query_id)
    except (FileNotFoundError, ValueError) as e:
        print(f"  · sin embedding denso para {query_id} ({e}); salto los 8 hybrid combos")
        return {}, {}

    rankings: dict = {}
    latencies: dict = {}
    for partner in config.HYBRID_SPARSE_VARIANTS:
        result = search.search(
            query=query_text,
            method="hybrid_rrf",
            size=size,
            scoring=partner,
            query_id=query_id,
        )
        rankings[f"{HYBRID_PREFIX}{partner}"] = [
            {"chunk_uuid": h["chunk_uuid"], "score": h["score"], "rank": i + 1}
            for i, h in enumerate(result["hits"])
        ]
        latencies[f"{HYBRID_PREFIX}{partner}"] = result.get("latency_ms")
    return rankings, latencies


def hydrate_pool(uuids: list[str]) -> list[dict]:
    """Trae el contenido de cada chunk desde OpenSearch en una sola request."""
    os_client = clients.get_opensearch()
    resp = os_client.mget(
        index=config.INDEX_CHUNKS,
        body={"ids": uuids},
        _source=_HYDRATE_FIELDS,
    )
    pool = []
    for doc in resp["docs"]:
        if not doc.get("found"):
            continue
        pool.append(doc["_source"])
    return pool


def ensure_retrieval_results_index(os_client) -> None:
    """Crea el índice retrieval_results si no existe. Idempotente."""
    if not os_client.indices.exists(index=config.INDEX_RETRIEVAL_RESULTS):
        os_client.indices.create(
            index=config.INDEX_RETRIEVAL_RESULTS,
            body=_RETRIEVAL_RESULTS_MAPPING,
        )
        print(f"[+] creado índice {config.INDEX_RETRIEVAL_RESULTS}")


def index_rankings_in_opensearch(
    query_id: str,
    query_text: str,
    rankings: dict,
    latencies: dict,
    size: int,
) -> None:
    """Ingesta una fila por (query_id, technique_name) en retrieval_results.

    El _id determinístico (`<query_id>::<technique_name>`) garantiza
    idempotencia: re-correr la misma query sobreescribe en lugar de
    duplicar filas.
    """
    os_client = clients.get_opensearch()
    ensure_retrieval_results_index(os_client)

    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def _actions():
        for technique_name, hits in rankings.items():
            yield {
                "_op_type": "index",
                "_index": config.INDEX_RETRIEVAL_RESULTS,
                "_id": f"{query_id}::{technique_name}",
                "_source": {
                    "run_id": str(uuid4()),
                    "query_id": query_id,
                    "query_text": query_text,
                    "technique_name": technique_name,
                    "timestamp": timestamp,
                    "size": size,
                    "latency_ms": latencies.get(technique_name),
                    "hits": hits,
                },
            }

    ok, errors = bulk(os_client, _actions(), raise_on_error=False)
    if errors:
        print(f"  [!] {len(errors)} errores al ingestar rankings: {errors[:1]}")
    os_client.indices.refresh(index=config.INDEX_RETRIEVAL_RESULTS)
    print(f"  → ingestado en {config.INDEX_RETRIEVAL_RESULTS}: " f"{ok} filas (una por técnica)")


def main(
    query_file: Path,
    output_dir: Path,
    size: int,
    shuffle: bool,
    seed: int,
) -> None:
    query = json.loads(query_file.read_text())
    query_id = query["query_id"]
    query_text = query["query_text"]

    print(f"[{query_id}] {query_text!r}")
    print("Recuperando top-k por técnica esparsa...")
    rankings, latencies = retrieve_all_sparse(query_text, size=size)

    print("Recuperando top-k por combo híbrido RRF (dense + sparse)...")
    hybrid_rankings, hybrid_latencies = retrieve_all_hybrid(query_text, query_id, size=size)
    # Mezclamos los dos dicts en uno. Las claves `rrf_<sparse>` no colisionan
    # con las sparse plain por construcción del prefijo.
    rankings.update(hybrid_rankings)
    latencies.update(hybrid_latencies)

    # Resumen de latencias por técnica (evidencia comparable end-to-end).
    for method, ms in latencies.items():
        print(f"  · {method}: {ms} ms")

    # Pool deduplicado, preservando orden de primera aparición.
    seen: set[str] = set()
    pool_uuids: list[str] = []
    for ranking in rankings.values():
        for hit in ranking:
            if hit["chunk_uuid"] not in seen:
                seen.add(hit["chunk_uuid"])
                pool_uuids.append(hit["chunk_uuid"])

    print(f"Pool sin repeticiones: {len(pool_uuids)} chunks únicos")

    pool = hydrate_pool(pool_uuids)

    if shuffle:
        random.Random(seed).shuffle(pool)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{query_id}.json"
    out_path.write_text(
        json.dumps(
            {
                "query_id": query_id,
                "query_text": query_text,
                "rankings": rankings,
                "latencies": latencies,
                "pool": pool,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"OK -> {out_path}")

    # Persistir rankings en OpenSearch (índice retrieval_results) para que
    # queden auditables y disponibles al computar métricas más adelante.
    index_rankings_in_opensearch(
        query_id=query_id,
        query_text=query_text,
        rankings=rankings,
        latencies=latencies,
        size=size,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument(
        "--no-shuffle",
        action="store_true",
        help="Desactiva la aleatorización del pool (útil para debug)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    main(
        query_file=args.query_file,
        output_dir=args.output_dir,
        size=args.size,
        shuffle=not args.no_shuffle,
        seed=args.seed,
    )
