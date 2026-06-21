"""Lee todos los judgments de una carpeta, los ingesta en OpenSearch y
genera un resumen consolidado.

Lo que hace:

1. Itera `judgments/*.json` (uno por query).
2. Crea (si no existe) el índice `ground_truth` con un mapping mínimo y
   bulk-indexa todos los judgments con id = "<query_id>::<chunk_uuid>"
   (idempotente: una re-corrida sobrescribe).
3. Imprime y guarda un resumen:
     - Cantidad de queries y de judgments.
     - Distribución de grados (0, 1, 2, 3).
     - Cantidad de fallidos (grade=-1, PARSE_ERROR del juez).
     - Breakdown por query: total y grado promedio.

Uso:
    python scripts/benchmark/ingest_judgments.py \\
        --judgments-dir scripts/benchmark/judgments \\
        --summary-file scripts/benchmark/summary.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Igual que retrieve_for_query.py: este script importa `from src import clients`,
# pero ejecutado como `python scripts/benchmark/ingest_judgments.py` la raiz del
# repo no esta en sys.path (solo scripts/benchmark/). `parents[2]` sube hasta la
# raiz del repo y la inserta al frente para que `import src` resuelva.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opensearchpy.helpers import streaming_bulk
from src import clients

GROUND_TRUTH_INDEX = "ground_truth"

GROUND_TRUTH_MAPPING = {
    "settings": {
        "index": {"number_of_shards": 1, "number_of_replicas": 0},
    },
    "mappings": {
        "properties": {
            "query_id": {"type": "keyword"},
            "query_text": {"type": "text"},
            "chunk_uuid": {"type": "keyword"},
            "relevance_grade": {"type": "integer"},
            "justification": {"type": "text"},
            "model": {"type": "keyword"},
            "judged_at": {"type": "date"},
        }
    },
}


def ensure_index(os_client) -> None:
    if not os_client.indices.exists(index=GROUND_TRUTH_INDEX):
        os_client.indices.create(index=GROUND_TRUTH_INDEX, body=GROUND_TRUTH_MAPPING)
        print(f"[+] creado índice {GROUND_TRUTH_INDEX}")


def load_all_judgments(judgments_dir: Path) -> list[dict]:
    """Aplana todos los archivos en una lista de dicts listos para ingesta."""
    rows: list[dict] = []
    for path in sorted(judgments_dir.glob("*_judgments.json")):
        data = json.loads(path.read_text())
        for j in data.get("judgments", []):
            rows.append(
                {
                    "query_id": data["query_id"],
                    "query_text": data["query_text"],
                    "model": data.get("model", ""),
                    "judged_at": data.get("judged_at"),
                    "chunk_uuid": j["chunk_uuid"],
                    "relevance_grade": j["relevance_grade"],
                    "justification": j.get("justification", ""),
                }
            )
    return rows


def bulk_ingest(os_client, rows: list[dict]) -> tuple[int, int]:
    def _actions():
        for r in rows:
            yield {
                "_op_type": "index",
                "_index": GROUND_TRUTH_INDEX,
                "_id": f"{r['query_id']}::{r['chunk_uuid']}",
                "_source": r,
            }

    ok = fail = 0
    for success, info in streaming_bulk(
        os_client, _actions(), raise_on_error=False, raise_on_exception=False
    ):
        if success:
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                print(f"  [fail] {info}")
    return ok, fail


def build_summary(rows: list[dict]) -> dict:
    by_query: dict[str, list[int]] = defaultdict(list)
    grade_dist: dict[int, int] = defaultdict(int)
    failed = 0

    for r in rows:
        g = r["relevance_grade"]
        if g == -1:
            failed += 1
            continue
        by_query[r["query_id"]].append(g)
        grade_dist[g] += 1

    per_query = {}
    for qid, grades in by_query.items():
        per_query[qid] = {
            "n_judgments": len(grades),
            "grade_mean": round(statistics.mean(grades), 3) if grades else None,
            "n_relevantes_2_o_3": sum(1 for g in grades if g >= 2),
        }

    # Distribucion empirica: en vez de fijarle al juez una cuota "al ojo"
    # (antes el prompt decia "no mas del 20-30% deberia ser grado 3"),
    # dejamos que cada chunk se juzgue por su merito absoluto y MEDIMOS la
    # distribucion resultante. Estos porcentajes son los que hay que reportar
    # y justificar, no asumir de antemano.
    total_validos = sum(grade_dist[g] for g in (0, 1, 2, 3))
    distribucion_porcentual = {
        str(g): round(100 * grade_dist[g] / total_validos, 1) if total_validos else 0.0
        for g in (0, 1, 2, 3)
    }
    porcentaje_relevantes = (
        round(100 * (grade_dist[2] + grade_dist[3]) / total_validos, 1) if total_validos else 0.0
    )

    return {
        "queries_evaluadas": len(by_query),
        "judgments_totales": sum(len(v) for v in by_query.values()),
        "judgments_fallidos_parse": failed,
        "distribucion_de_grados": {
            "0": grade_dist[0],
            "1": grade_dist[1],
            "2": grade_dist[2],
            "3": grade_dist[3],
        },
        "distribucion_porcentual": distribucion_porcentual,
        "porcentaje_relevantes_2_o_3": porcentaje_relevantes,
        "por_query": per_query,
    }


def print_summary(summary: dict) -> None:
    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Queries evaluadas:      {summary['queries_evaluadas']}")
    print(f"  Judgments totales:      {summary['judgments_totales']}")
    print(f"  Fallidos (PARSE_ERROR): {summary['judgments_fallidos_parse']}")
    print()
    print("  Distribución de grados (conteo y % sobre judgments válidos):")
    for g in ("0", "1", "2", "3"):
        n = summary["distribucion_de_grados"][g]
        pct = summary["distribucion_porcentual"][g]
        print(f"    {g}: {n}  ({pct}%)")
    print(f"  Relevantes (grado >= 2): {summary['porcentaje_relevantes_2_o_3']}%")
    print()
    print("  Por query:")
    for qid, info in sorted(summary["por_query"].items()):
        print(
            f"    {qid}: n={info['n_judgments']:<3} "
            f"media={info['grade_mean']}  "
            f"relevantes(≥2)={info['n_relevantes_2_o_3']}"
        )


def main(judgments_dir: Path, summary_file: Path | None) -> None:
    if not judgments_dir.is_dir():
        sys.exit(f"[x] no existe la carpeta {judgments_dir}")

    rows = load_all_judgments(judgments_dir)
    if not rows:
        print(
            "[!] no se encontraron archivos *_judgments.json en "
            f"{judgments_dir}. Se genera un resumen parcial vacío."
        )

    os_client = clients.get_opensearch()
    ensure_index(os_client)

    print(f"Ingestando {len(rows)} judgments en {GROUND_TRUTH_INDEX}...")
    ok, fail = bulk_ingest(os_client, rows)
    print(f"  ok: {ok}   fail: {fail}")

    os_client.indices.refresh(index=GROUND_TRUTH_INDEX)

    summary = build_summary(rows)
    print_summary(summary)

    if summary_file is not None:
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n[+] resumen guardado en {summary_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgments-dir", type=Path, required=True)
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Si se entrega, guarda el resumen como JSON.",
    )
    args = parser.parse_args()

    main(judgments_dir=args.judgments_dir, summary_file=args.summary_file)
