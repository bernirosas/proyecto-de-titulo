"""Dry-run: cuántos juicios nuevos hacen falta para agregar híbrido al benchmark.

Para cada una de las 31 queries y cada uno de los 8 combos hybrid_rrf
(uno por sparse partner), corre el retrieve top-10 con la pool de fusión
a depth=50, unifica los `chunk_uuid` por query, y compara contra el pool
existente en `scripts/benchmark/pools/qNNN.json`.

NO incluye un ranking denso puro (decisión explícita: el benchmark sólo
evalúa híbridos contra los sparse existentes — el lado denso aislado
no es de interés para esta tesis).

NO llama al LLM-judge. NO modifica los pools en disco. NO toca el índice
`retrieval_results` de OpenSearch. Solo cuenta y reporta.

Salida (stdout):
    - Total de pares (query, chunk_uuid) nuevos que necesitan juicio.
    - Desglose por combo híbrido.
    - Top-5 queries con más juicios nuevos.

Uso (con el stack corriendo: opensearch + qdrant + queries_dense.json):
    docker compose run --rm app python scripts/benchmark/dry_run_hybrid_pools.py

Tarda ~30 segundos (no carga SPLADE de cold; usa retrieve_all-style warm cache).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Como retrieve_for_query.py: agregar la raíz del repo al sys.path para
# que `from src import ...` resuelva cuando se ejecuta como script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config, search  # noqa: E402

QUERIES_DIR = Path("scripts/benchmark/queries")
POOLS_DIR = Path("scripts/benchmark/pools")
TOP_K = 10  # mismo top-k que el benchmark sparse existente
HYBRID_PARTNERS = list(config.HYBRID_SPARSE_VARIANTS.keys())


def load_existing_pool(query_id: str) -> set[str]:
    """Devuelve el conjunto de chunk_uuid ya juzgados para esa query."""
    path = POOLS_DIR / f"{query_id}.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["chunk_uuid"] for item in data.get("pool", []) if "chunk_uuid" in item}


def retrieve_hybrid_top_k(query_text: str, query_id: str, partner: str, top_k: int) -> list[str]:
    """Top-k del ranking híbrido (dense + sparse partner vía RRF)."""
    result = search.search(
        query=query_text,
        method="hybrid_rrf",
        size=top_k,
        scoring=partner,
        query_id=query_id,
    )
    return [h["chunk_uuid"] for h in result["hits"] if h.get("chunk_uuid")]


def main() -> int:
    query_files = sorted(QUERIES_DIR.glob("q*.json"))
    if not query_files:
        print(f"[x] no hay queries en {QUERIES_DIR}", file=sys.stderr)
        return 1

    print(f"[dry-run] {len(query_files)} queries × {len(HYBRID_PARTNERS)} combos híbridos")
    print()

    # Acumuladores
    new_by_technique: dict[str, set[tuple[str, str]]] = defaultdict(set)
    new_by_query: dict[str, set[str]] = defaultdict(set)

    for i, qf in enumerate(query_files, 1):
        data = json.loads(qf.read_text(encoding="utf-8"))
        qid = data["query_id"]
        qtext = data["query_text"]
        existing = load_existing_pool(qid)
        print(f"  [{i:2d}/{len(query_files)}] {qid}: pool existente = {len(existing)} chunks")

        # hybrid_rrf con cada sparse partner
        for partner in HYBRID_PARTNERS:
            try:
                hybrid_top = retrieve_hybrid_top_k(qtext, qid, partner, TOP_K)
            except Exception as e:
                print(f"      ! hybrid+{partner} FALLÓ: {e}", file=sys.stderr)
                continue
            for uuid in hybrid_top:
                if uuid not in existing:
                    new_by_technique[f"hybrid+{partner}"].add((qid, uuid))
                    new_by_query[qid].add(uuid)

    # ----- Reporte -----
    print()
    print("=" * 60)
    print("Resumen")
    print("=" * 60)
    print()
    print("Juicios NUEVOS por combo (chunks que NO estaban en el pool existente):")
    print()
    print(f"  {'combo':<35} {'nuevos':>8} {'/queries':>10}")
    print(f"  {'-' * 35} {'-' * 8} {'-' * 10}")
    grand_total_pairs: set[tuple[str, str]] = set()
    for partner in HYBRID_PARTNERS:
        tech = f"hybrid+{partner}"
        pairs = new_by_technique.get(tech, set())
        per_q = len(pairs) / len(query_files) if query_files else 0
        print(f"  {tech:<35} {len(pairs):>8} {per_q:>10.1f}")
        grand_total_pairs |= pairs

    print()
    print(f"Total pares (query, chunk) únicos a juzgar: {len(grand_total_pairs)}")
    print(f"   (con dedup entre los {len(HYBRID_PARTNERS)} combos — un chunk que aparece en")
    print("    varios rankings cuenta una sola vez)")

    print()
    print("Top-5 queries con más juicios nuevos:")
    top_queries = sorted(new_by_query.items(), key=lambda kv: -len(kv[1]))[:5]
    for qid, uuids in top_queries:
        print(f"  {qid}: +{len(uuids)} chunks nuevos")

    print()
    print("Estimación de costo:")
    print(f"  - Llamadas Gemini para juzgar: {len(grand_total_pairs)}")
    print(f"  - ~1-2s por juicio serial → ~{len(grand_total_pairs) * 1.5 / 60:.0f} minutos")
    print(
        f"  - Gemini 2.5-flash-lite: ~$0.0005 / juicio → ${len(grand_total_pairs) * 0.0005:.2f} total"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
