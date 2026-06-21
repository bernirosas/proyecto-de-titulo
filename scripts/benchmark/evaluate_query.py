"""Evalúa las técnicas de retrieval para una sola query.

Une los rankings de `scripts/benchmark/pools/qNNN.json` con los grados de
`scripts/benchmark/judgments/qNNN_judgments.json` y calcula, por técnica:

  - **Promedio de relevancia** (mean grade) en top-1, top-3, top-5 y top-10.
    Es la métrica que solicitamos como observación directa: el promedio de
    los grados 0-3 asignados por el juez a los primeros k chunks. Mayor es
    mejor (3 = altamente relevante, 0 = irrelevante).

  - **Precision@k**: fracción de chunks con grado **exactamente 3**
    (altamente relevante) en los primeros k. Es el criterio más estricto:
    solo cuentan los chunks que el juez consideró "altamente relevantes",
    no los meramente útiles. P@5 = 0.8 significa "4 de los 5 primeros
    chunks responden directa y sustantivamente la consulta".

  - **n_failed**: cantidad de judgments con grado -1 (PARSE_ERROR del
    juez) que se omiten del cómputo. Si hay muchos, las métricas son
    poco confiables y conviene re-correr el juez.

  - **Latencia** (ms): leída del campo `latencies` del pool JSON
    (medida por `retrieve_for_query.py` con una corrida por técnica).
    Se muestra como columna extra a la derecha de la tabla para
    contrastar calidad vs costo end-to-end. Si el pool no trae
    `latencies` (corrida vieja) la columna queda con guión.

Salida:
  - Tabla a stdout: una fila por técnica, columnas mean_grade y P@k
    para los cuatro valores de k, más latencia en ms.
  - Identificación de la técnica ganadora por top-10 mean_grade.
  - JSON opcional con todas las métricas si se entrega --output-file.

Uso:
  python scripts/benchmark/evaluate_query.py \\
      --pool-file scripts/benchmark/pools/q001.json \\
      --judgments-file scripts/benchmark/judgments/q001_judgments.json \\
      --output-file scripts/benchmark/evaluations/q001_eval.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

# Valores de k para los que se reportan métricas. Cubren tanto el extremo
# (top-1) como el ranking completo (top-10), pasando por los típicos de
# literatura de retrieval (top-3, top-5).
K_VALUES = (1, 3, 5, 10)

# Umbral de relevancia para Precision@k: solo chunks con grado >= 3
# cuentan como "hits". Es el criterio estricto: solo cuentan los
# fragmentos que el juez consideró "altamente relevantes" (responden
# directa y sustantivamente la consulta), no los meramente útiles
# (grado 2). Se prefiere por sobre el umbral >= 2 porque deja más
# espacio a las técnicas para diferenciarse: si la mayoría devuelve
# grado 2 al inicio, P@k=2 es alto pero plano; con umbral 3 las
# diferencias entre técnicas se hacen visibles.
RELEVANCE_THRESHOLD = 3


def load_judgments_map(path: Path) -> dict[str, int]:
    """Devuelve un dict {chunk_uuid: relevance_grade}."""
    data = json.loads(path.read_text())
    return {j["chunk_uuid"]: j["relevance_grade"] for j in data.get("judgments", [])}


def evaluate_ranking(
    ranking: list[dict],
    judgments: dict[str, int],
    k: int,
) -> dict:
    """Calcula las métricas para los primeros k chunks de un ranking.

    Reglas de cómputo:
      - Si un chunk no tiene judgment, cuenta como `n_missing` y se omite
        del promedio (no es lo mismo que grado 0 — no sabemos su grado).
      - Si un chunk tiene grado -1 (PARSE_ERROR del juez), cuenta como
        `n_failed` y se omite del promedio. Si todos los chunks del top-k
        están fallidos, devuelve mean_grade=None para que el reporte sea
        explícito en lugar de mostrar un cero engañoso.
    """
    top_k = ranking[:k]
    grades: list[int] = []
    missing = 0
    failed = 0
    for hit in top_k:
        uuid = hit["chunk_uuid"]
        g = judgments.get(uuid)
        if g is None:
            missing += 1
        elif g == -1:
            failed += 1
        else:
            grades.append(g)

    if not grades:
        return {
            "mean_grade": None,
            "precision_at_k": None,
            "n_judged": 0,
            "n_missing": missing,
            "n_failed": failed,
        }
    return {
        "mean_grade": round(statistics.mean(grades), 3),
        "precision_at_k": round(
            sum(1 for g in grades if g >= RELEVANCE_THRESHOLD) / len(grades), 3
        ),
        "n_judged": len(grades),
        "n_missing": missing,
        "n_failed": failed,
    }


def evaluate_all_techniques(
    rankings: dict[str, list[dict]],
    judgments: dict[str, int],
) -> dict:
    """Aplica evaluate_ranking a cada técnica y cada k de K_VALUES."""
    out: dict = {}
    for technique, ranking in rankings.items():
        out[technique] = {f"top_{k}": evaluate_ranking(ranking, judgments, k) for k in K_VALUES}
    return out


def _latency_ms(latencies: dict | None, technique: str) -> float | None:
    """Devuelve la latencia en ms de una técnica, o None si no está.

    Es robusto a dos shapes en el pool JSON:
      - `{tecnica: float_ms}` — shape canónico de `retrieve_for_query.py`.
      - `{tecnica: {"mean": float_ms, ...}}` — shape legacy si en algún
        momento se experimentó con agregación estadística. Se extrae `mean`.
    """
    if not latencies:
        return None
    val = latencies.get(technique)
    if val is None:
        return None
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, dict):
        m = val.get("mean")
        return float(m) if m is not None else None
    return None


def format_table(metrics: dict, latencies: dict | None = None) -> str:
    """Construye la tabla técnica × k con mean_grade, P@k y latencia.

    Se separa de la impresión para poder volcar el mismo contenido a stdout
    y a un archivo .txt (companion del JSON de métricas). El formato es ASCII
    para que se vea bien tanto en terminal como en un editor sin renderizado.

    Si `latencies` es None (o no contiene una técnica), la columna de
    latencia sale con guión.
    """
    lines = []
    header = f"  {'Técnica':<22}"
    for k in K_VALUES:
        header += f"  {'top-' + str(k) + ' mean':>13}  {'top-' + str(k) + ' P@k':>12}"
    header += f"  {'lat ms':>10}"
    total_width = len(header)
    lines.append("=" * total_width)
    lines.append(header)
    lines.append("-" * total_width)
    for technique, by_k in sorted(metrics.items()):
        row = f"  {technique:<22}"
        for k in K_VALUES:
            m = by_k[f"top_{k}"]
            mean = f"{m['mean_grade']:.3f}" if m["mean_grade"] is not None else "—"
            prec = f"{m['precision_at_k']:.3f}" if m["precision_at_k"] is not None else "—"
            row += f"  {mean:>13}  {prec:>12}"
        lat = _latency_ms(latencies, technique)
        lat_str = f"{lat:.1f}" if lat is not None else "—"
        row += f"  {lat_str:>10}"
        lines.append(row)
    lines.append("=" * total_width)
    return "\n".join(lines)


def print_table(metrics: dict, latencies: dict | None = None) -> None:
    """Imprime a stdout la tabla generada por `format_table`."""
    print()
    print(format_table(metrics, latencies))


def print_diagnostics(metrics: dict) -> None:
    """Reporta cuántos judgments fallidos hubo (-1) y faltantes."""
    total_failed = 0
    total_missing = 0
    for by_k in metrics.values():
        top_10 = by_k.get("top_10", {})
        total_failed = max(total_failed, top_10.get("n_failed", 0))
        total_missing = max(total_missing, top_10.get("n_missing", 0))
    if total_failed or total_missing:
        print()
        print("  Diagnóstico:")
        if total_failed:
            print(
                f"    {total_failed} chunks con grade=-1 (PARSE_ERROR) omitidos del cómputo. "
                "Re-corra el juez para limpiarlos."
            )
        if total_missing:
            print(
                f"    {total_missing} chunks en ranking sin judgment correspondiente. "
                "Verifique consistencia pool ↔ judgments."
            )


def identify_winner(metrics: dict) -> tuple[str | None, float | None]:
    """Devuelve la técnica con mayor mean_grade en top-10 (o None si ninguna)."""
    valid = [
        (tech, by_k["top_10"]["mean_grade"])
        for tech, by_k in metrics.items()
        if by_k["top_10"]["mean_grade"] is not None
    ]
    if not valid:
        return None, None
    winner = max(valid, key=lambda x: x[1])
    return winner


def main(pool_file: Path, judgments_file: Path, output_file: Path | None) -> None:
    if not pool_file.is_file():
        sys.exit(f"[x] no existe {pool_file}")
    if not judgments_file.is_file():
        sys.exit(f"[x] no existe {judgments_file}")

    pool_data = json.loads(pool_file.read_text())
    rankings = pool_data["rankings"]
    latencies = pool_data.get("latencies")  # opcional; tolera pools viejos
    judgments = load_judgments_map(judgments_file)

    print(f"Query: {pool_data['query_id']} — {pool_data['query_text']!r}")
    print(f"Judgments cargados: {len(judgments)}")
    print(f"Técnicas evaluadas: {len(rankings)}")

    metrics = evaluate_all_techniques(rankings, judgments)
    print_table(metrics, latencies)
    print_diagnostics(metrics)

    winner, score = identify_winner(metrics)
    if winner:
        print(f"\n  → Mejor técnica por top-10 mean_grade: {winner} ({score:.3f})")
    else:
        print(
            "\n  [!] No se pudo identificar técnica ganadora "
            "(todos los top-10 sin judgments válidos)."
        )

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(
                {
                    "query_id": pool_data["query_id"],
                    "query_text": pool_data["query_text"],
                    "k_values": list(K_VALUES),
                    "relevance_threshold": RELEVANCE_THRESHOLD,
                    "metrics": metrics,
                    "latencies": latencies,
                    "winner_top10": winner,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"\n[+] métricas guardadas en {output_file}")

        # Companion .txt con la tabla legible. Se guarda automáticamente
        # junto al JSON para que quede como evidencia en el repo sin que
        # el integrante tenga que copiarla a mano desde stdout.
        txt_path = output_file.with_suffix(".txt")
        report_lines = [
            f"Query: {pool_data['query_id']} — {pool_data['query_text']}",
            f"Judgments cargados: {len(judgments)}",
            f"Técnicas evaluadas: {len(rankings)}",
            f"Umbral de relevancia (P@k): grado >= {RELEVANCE_THRESHOLD}",
            "",
            format_table(metrics, latencies),
        ]
        if winner:
            report_lines.append(
                f"\n  → Mejor técnica por top-10 mean_grade: {winner} ({score:.3f})"
            )
        else:
            report_lines.append(
                "\n  [!] No se pudo identificar técnica ganadora "
                "(todos los top-10 sin judgments válidos)."
            )
        txt_path.write_text("\n".join(report_lines) + "\n")
        print(f"[+] tabla legible guardada en {txt_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pool-file",
        type=Path,
        required=True,
        help="JSON con los rankings por técnica (output de retrieve_for_query.py)",
    )
    parser.add_argument(
        "--judgments-file",
        type=Path,
        required=True,
        help="JSON con los grados del juez LLM (output de judge_pool.py)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Si se entrega, guarda las métricas como JSON",
    )
    args = parser.parse_args()

    main(
        pool_file=args.pool_file,
        judgments_file=args.judgments_file,
        output_file=args.output_file,
    )
