"""Consolida los reportes de evaluación de todas las queries del benchmark.

Lee `scripts/benchmark/evaluations/qNNN_eval.json` para cada query
disponible y produce **tres** archivos Markdown:

  - `reporte_sparse.md`     → las 8 técnicas esparsas puras.
  - `reporte_hibrido.md`    → los 8 combos híbridos RRF (`rrf_<sparse>`).
  - `reporte_comparativo.md`→ head-to-head sparse-vs-híbrido, ranking
                              global con las 16 técnicas mezcladas, y
                              análisis de cuándo conviene cada lado.

Cada uno de los dos primeros sigue la misma estructura:

  1. **Resumen global por técnica**: mean / p50 / p95 a lo largo de todas
     las queries, para los tres indicadores que importan en la tesis:
       - mean_grade @ top-10 (calidad principal)
       - P@5 (presencia de chunks altamente relevantes al inicio)
       - latencia end-to-end (costo)

  2. **Desglose por tema**: las queries se asignan al tema correspondiente
     según el rango de `query_id` (ver `TEMA_RANGES` abajo) o bien por el
     campo `tema` opcional del JSON de la query. Por cada tema se reportan
     las mismas tres métricas y la técnica ganadora.

  3. **Ranking final**: tabla con la técnica ganadora del benchmark
     (mayor mean del mean_grade@10 cross-query) y comparación con la
     baseline.

El comparativo agrega encima una tabla head-to-head donde cada fila pares
un sparse `X` con su contraparte `rrf_X`, mostrando deltas de calidad,
precisión y latencia, más una vista de las técnicas top global mezcladas.

Uso:
    python scripts/benchmark/consolidate_evaluations.py \\
        --evaluations-dir scripts/benchmark/evaluations \\
        --queries-dir scripts/benchmark/queries \\
        --output-dir scripts/benchmark
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

# Prefijo de las técnicas híbridas en los rankings/latencies de los pools.
# Mantener sincronizado con `HYBRID_PREFIX` en retrieve_for_query.py.
HYBRID_PREFIX = "rrf_"


def is_hybrid(technique: str) -> bool:
    return technique.startswith(HYBRID_PREFIX)


# Valores de k que el comparativo reporta para mean_grade y P@k.
# Tienen que coincidir con los del evaluate_query.py para que la
# trazabilidad qNNN_eval.txt ↔ reporte sea directa.
K_VALUES_REPORT: tuple[int, ...] = (1, 3, 5, 10)


def sparse_partner_of(technique: str) -> str:
    """Para una técnica `rrf_p1_bm25` devuelve `p1_bm25`. No-op para sparse."""
    if is_hybrid(technique):
        return technique[len(HYBRID_PREFIX) :]
    return technique


# Asignación de query_id (entero) a tema. Cada rango se define como
# (lo, hi) inclusive. La idea es que cada integrante haya curado un bloque
# de ~5 queries con un foco temático claro, lo que facilita comparar
# técnicas en distintos sub-dominios del corpus inmobiliario.
TEMA_RANGES: list[tuple[str, int, int]] = [
    ("Arrendamientos", 1, 5),
    ("Compraventa", 6, 10),
    ("Copropiedad / Propiedad horizontal", 11, 15),
    ("Tributación inmobiliaria", 16, 20),
    ("Recursos sobre bienes raíces", 21, 25),
    ("Jurisprudencia de inmuebles", 26, 30),
]
# Tema explícito para queries fuera de los rangos (típicamente la query
# semilla q000, que usamos como sanity check del pipeline). Se reporta
# aparte para que no contamine los promedios temáticos.
TEMA_SEED = "Sanity check (seed)"


def _tema_for(query_id: str, override: str | None = None) -> str:
    """Asigna un tema a una query.

    Prioridad: override explícito del JSON (campo `tema`) > rango por id.
    Si el id no calza con ningún rango y no hay override, queda como seed.
    """
    if override:
        return override
    try:
        n = int(query_id.lstrip("q"))
    except ValueError:
        return TEMA_SEED
    for tema, lo, hi in TEMA_RANGES:
        if lo <= n <= hi:
            return tema
    return TEMA_SEED


def _stats(samples: list[float]) -> dict:
    """mean / p50 / p95 sobre una lista de valores. None si está vacía."""
    if not samples:
        return {"mean": None, "p50": None, "p95": None, "n": 0}
    s = sorted(samples)
    n = len(s)
    return {
        "mean": round(sum(s) / n, 3),
        "p50": round(s[n // 2], 3),
        "p95": round(s[max(0, min(n - 1, int((n * 0.95) + 0.5) - 1))], 3),
        "n": n,
    }


def _fmt(v) -> str:
    """Formatea un número con 3 decimales, o '—' si es None."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _fmt_ms(v) -> str:
    """Formatea ms con 1 decimal, o '—' si es None."""
    return f"{v:.1f}" if v is not None else "—"


def load_evaluations(evaluations_dir: Path, queries_dir: Path | None) -> list[dict]:
    """Lee todos los qNNN_eval.json y los enriquece con el tema asignado.

    Si `queries_dir` se entrega y un query JSON tiene campo `tema`, ese
    override prevalece sobre el rango. Sin queries_dir cae al rango puro.
    """
    out: list[dict] = []
    for eval_file in sorted(evaluations_dir.glob("q*_eval.json")):
        data = json.loads(eval_file.read_text())
        qid = data["query_id"]

        tema_override = None
        if queries_dir is not None:
            matches = list(queries_dir.glob(f"{qid}_*.json"))
            if matches:
                try:
                    qdata = json.loads(matches[0].read_text())
                    tema_override = qdata.get("tema")
                except (json.JSONDecodeError, OSError):
                    pass

        data["_tema"] = _tema_for(qid, tema_override)
        out.append(data)
    return out


def _latency_of(eval_data: dict, technique: str) -> float | None:
    """Extrae la latencia de una técnica, tolerando float y dict legacy."""
    lat = (eval_data.get("latencies") or {}).get(technique)
    if lat is None:
        return None
    if isinstance(lat, int | float):
        return float(lat)
    if isinstance(lat, dict):
        m = lat.get("mean")
        return float(m) if m is not None else None
    return None


def aggregate(
    evaluations: list[dict],
    tech_filter: Callable[[str], bool] | None = None,
) -> dict:
    """Agrega métricas por técnica a lo largo de la lista de evaluaciones.

    Devuelve un dict `{tecnica: {mean_grade_<k>: {mean, p50, p95}, ...}}`
    con `mean_grade_<k>` y `p_at_<k>` para cada k en `K_VALUES_REPORT`
    (1, 3, 5, 10), más `lat_ms`. Las claves `mean_grade_10` y `p_at_5`
    se preservan adrede porque varios callers existentes (y tests) las
    referencian por nombre — los demás k son adición pura, no rompen
    compatibilidad.

    Si `tech_filter` se provee, solo se incluyen las técnicas para las
    cuales `tech_filter(tech_name)` es True. Esto permite producir el
    reporte sparse (filter: no `is_hybrid`) y el reporte híbrido (filter:
    `is_hybrid`) sin duplicar lógica.
    """

    def _empty_samples() -> dict[str, list[float]]:
        keys = [f"mean_grade_{k}" for k in K_VALUES_REPORT]
        keys += [f"p_at_{k}" for k in K_VALUES_REPORT]
        keys.append("lat_ms")
        return {k: [] for k in keys}

    by_tech: dict[str, dict[str, list[float]]] = defaultdict(_empty_samples)

    for ev in evaluations:
        metrics = ev.get("metrics", {})
        for tech, by_k in metrics.items():
            if tech_filter is not None and not tech_filter(tech):
                continue
            for k in K_VALUES_REPORT:
                top = by_k.get(f"top_{k}", {})
                if top.get("mean_grade") is not None:
                    by_tech[tech][f"mean_grade_{k}"].append(top["mean_grade"])
                if top.get("precision_at_k") is not None:
                    by_tech[tech][f"p_at_{k}"].append(top["precision_at_k"])
            lat = _latency_of(ev, tech)
            if lat is not None:
                by_tech[tech]["lat_ms"].append(lat)

    return {
        tech: {key: _stats(values) for key, values in samples.items()}
        for tech, samples in by_tech.items()
    }


def _technique_table(aggregated: dict, metric_key: str, formatter) -> str:
    """Construye una tabla Markdown técnica × estadísticas para una métrica.

    Para `mean_grade_10` y `p_at_5` (calidad/precisión): orden de columnas
    mean | p50 | p95 y ordenamiento descendente por mean. Las distribuciones
    son acotadas (max 3.0 o 1.0), el mean es representativo y conviene
    liderar con él.

    Para `lat_ms` (latencia): orden de columnas p50 | p95 | mean y
    ordenamiento ascendente por p50. La distribución es de cola larga
    (el cold-start de la primera query del proceso warm tira el mean para
    arriba), así que el p50 es la métrica honesta de steady-state. Se
    deja el mean al final como referencia secundaria.
    """
    is_latency = metric_key == "lat_ms"

    if is_latency:
        # Unit explícito en el header — la columna está en milisegundos.
        header = "| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |"
    else:
        header = "| Técnica | mean | p50 | p95 | n |"
    lines = [header, "|---|---:|---:|---:|---:|"]

    rows = [(tech, stats[metric_key]) for tech, stats in aggregated.items()]
    # Calidad: mayor mean primero. Latencia: menor p50 primero (más rápida arriba).
    if is_latency:
        rows.sort(key=lambda x: (x[1]["p50"] is None, x[1]["p50"] or 0))
    else:
        rows.sort(key=lambda x: (x[1]["mean"] is None, -(x[1]["mean"] or 0)))

    for tech, m in rows:
        if is_latency:
            lines.append(
                f"| `{tech}` | {formatter(m['p50'])} | {formatter(m['p95'])} | "
                f"{formatter(m['mean'])} | {m['n']} |"
            )
        else:
            lines.append(
                f"| `{tech}` | {formatter(m['mean'])} | {formatter(m['p50'])} | "
                f"{formatter(m['p95'])} | {m['n']} |"
            )
    return "\n".join(lines)


def _cross_k_table(aggregated: dict, prefix: str, formatter) -> str:
    """Tabla Markdown técnica × k para una métrica que se reporta a varios k.

    Cada columna es el `mean` cross-query del valor en ese k. Útil para
    visualizar la degradación de la métrica a medida que aumenta k
    (p. ej. si `mean_grade@1` es alto pero `mean_grade@10` cae mucho,
    la técnica concentra relevancia en el top pero degrada rápido).

    Args:
        prefix: prefijo de las claves del dict agregado, sin el `_<k>`.
                Para mean_grade pasar `"mean_grade"`; para P@k pasar
                `"p_at"`. El helper compone `<prefix>_<k>` por cada k.
        formatter: función de formato del valor (e.g. `_fmt` para
                números con 3 decimales).

    Ordenamiento: descendente por el mean del k mayor (top-10 para
    mean_grade / P@k). La técnica más fuerte sobre el ranking completo
    aparece arriba.
    """
    header_k = " | ".join(f"top-{k}" for k in K_VALUES_REPORT)
    lines = [
        f"| Técnica | {header_k} | n |",
        "|---|" + "---:|" * (len(K_VALUES_REPORT) + 1),
    ]

    primary_key = f"{prefix}_{K_VALUES_REPORT[-1]}"
    rows = sorted(
        aggregated.items(),
        key=lambda kv: (
            kv[1][primary_key]["mean"] is None,
            -(kv[1][primary_key]["mean"] or 0),
        ),
    )
    for tech, stats in rows:
        n = stats[primary_key]["n"]
        cells = " | ".join(formatter(stats[f"{prefix}_{k}"]["mean"]) for k in K_VALUES_REPORT)
        lines.append(f"| `{tech}` | {cells} | {n} |")
    return "\n".join(lines)


def _winner_of(aggregated: dict) -> tuple[str | None, float | None]:
    """Devuelve la técnica con mayor mean(mean_grade@10) cross-query."""
    valid = [
        (tech, stats["mean_grade_10"]["mean"])
        for tech, stats in aggregated.items()
        if stats["mean_grade_10"]["mean"] is not None
    ]
    if not valid:
        return None, None
    return max(valid, key=lambda x: x[1])


def build_report(
    evaluations: list[dict],
    title: str = "Reporte consolidado del benchmark",
    subtitle: str | None = None,
    tech_filter: Callable[[str], bool] | None = None,
    judge_model: str | None = None,
) -> str:
    """Construye un reporte Markdown completo para un subconjunto de técnicas.

    `tech_filter` selecciona qué técnicas incluir en el reporte; si es
    None, se incluyen todas. El `title` y `subtitle` permiten que el
    mismo código genere reportes sparse, híbrido y comparativo con
    cabeceras distintas.
    """
    if not evaluations:
        return f"# {title}\n\nSin queries evaluadas.\n"

    # Agrupar por tema.
    by_tema: dict[str, list[dict]] = defaultdict(list)
    for ev in evaluations:
        by_tema[ev["_tema"]].append(ev)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    if subtitle:
        lines.append(f"_{subtitle}_")
        lines.append("")
    lines.append(
        f"**Queries evaluadas**: {len(evaluations)} " f"({len(by_tema)} temas representados)"
    )
    if judge_model:
        lines.append(f"**Modelo juez (LLM)**: `{judge_model}`")
    lines.append("**Métricas reportadas**: mean, mediana (p50), percentil 95")
    lines.append("")
    lines.append(
        "Las estadísticas son agregaciones cross-query: cada técnica recibe "
        "un valor por query (un `mean_grade@10`, un `P@5`, una latencia) "
        "y de esos valores se sacan mean / p50 / p95. Esto refleja cómo se "
        "comporta cada técnica en distintas consultas del dominio, no "
        "varianza intra-query."
    )
    lines.append("")

    # --- Resumen global -----------------------------------------------------
    global_agg = aggregate(evaluations, tech_filter=tech_filter)
    if not global_agg:
        lines.append("> Sin técnicas que cumplan el filtro aplicado.")
        return "\n".join(lines) + "\n"
    winner, winner_score = _winner_of(global_agg)

    lines.append("## Resumen global")
    lines.append("")
    if winner:
        lines.append(
            f"**Técnica ganadora**: `{winner}` "
            f"(mean del `mean_grade@10` cross-query = {winner_score:.3f})"
        )
        lines.append("")

    lines.append("### Calidad: `mean_grade` por k (cross-query)")
    lines.append("")
    lines.append(
        "Promedio cross-query de la relevancia (escala 0-3) en los primeros "
        "k chunks, con k ∈ {1, 3, 5, 10}. Permite ver cómo cae la calidad "
        "a medida que aumenta k: una técnica con `top-1` alto pero `top-10` "
        "bajo concentra los relevantes al principio del ranking."
    )
    lines.append("")
    lines.append(_cross_k_table(global_agg, "mean_grade", _fmt))
    lines.append("")

    lines.append("### Calidad: `mean_grade @ top-10` (varianza)")
    lines.append("")
    lines.append(
        "Mismo `mean_grade@10` pero mostrando la varianza cross-query "
        "(mean / p50 / p95). Útil para distinguir técnicas con calidad "
        "media similar pero distinta robustez ante queries difíciles."
    )
    lines.append("")
    lines.append(_technique_table(global_agg, "mean_grade_10", _fmt))
    lines.append("")

    lines.append("### Precisión: `P@k` por k (cross-query)")
    lines.append("")
    lines.append(
        "Fracción de los primeros k chunks que el juez consideró "
        "*altamente relevantes* (grado 3, umbral estricto), promediada "
        "cross-query. Sigue el mismo patrón de degradación que mean_grade."
    )
    lines.append("")
    lines.append(_cross_k_table(global_agg, "p_at", _fmt))
    lines.append("")

    lines.append("### Precisión: `P@5` (varianza)")
    lines.append("")
    lines.append("Mismo `P@5` pero con varianza cross-query (mean / p50 / p95).")
    lines.append("")
    lines.append(_technique_table(global_agg, "p_at_5", _fmt))
    lines.append("")

    lines.append("### Latencia end-to-end")
    lines.append("")
    lines.append(
        "Tiempo de respuesta de cada técnica (preproc/encoder + I/O a "
        "OpenSearch) en milisegundos. NO incluye highlights ni "
        "post-procesamiento. Se lidera con p50 porque la distribución "
        "tiene cola larga por cold-start de la primera query del proceso."
    )
    lines.append("")
    lines.append(_technique_table(global_agg, "lat_ms", _fmt_ms))
    lines.append("")

    # --- Desglose por tema --------------------------------------------------
    lines.append("## Desglose por tema")
    lines.append("")
    lines.append(
        "Para cada tema se reportan las mismas tres métricas. Si una técnica "
        "destaca en un tema pero no en otros, ahí está la pista experimental."
    )
    lines.append("")

    # Tema con id_lo más bajo aparece primero (orden natural por número de query).
    def _tema_order(tema: str) -> int:
        for t, lo, _ in TEMA_RANGES:
            if t == tema:
                return lo
        return 999  # Seed y temas desconocidos al final.

    for tema in sorted(by_tema.keys(), key=_tema_order):
        evs = by_tema[tema]
        agg = aggregate(evs, tech_filter=tech_filter)
        if not agg:
            continue
        w, score = _winner_of(agg)
        qids = sorted(ev["query_id"] for ev in evs)

        lines.append(f"### {tema}")
        lines.append("")
        lines.append(f"**Queries**: {', '.join(f'`{q}`' for q in qids)}  " f"(N = {len(evs)})")
        if w:
            lines.append(f"**Ganadora del tema**: `{w}` " f"(mean `mean_grade@10` = {score:.3f})")
        lines.append("")
        lines.append("**Calidad** (`mean_grade` por k, cross-query del tema):")
        lines.append("")
        lines.append(_cross_k_table(agg, "mean_grade", _fmt))
        lines.append("")
        lines.append("**Precisión** (`P@k` por k, cross-query del tema):")
        lines.append("")
        lines.append(_cross_k_table(agg, "p_at", _fmt))
        lines.append("")
        lines.append("**Latencia** end-to-end:")
        lines.append("")
        lines.append(_technique_table(agg, "lat_ms", _fmt_ms))
        lines.append("")

    # --- Ranking final ------------------------------------------------------
    lines.append("## Ranking final (calidad vs costo)")
    lines.append("")
    lines.append(
        "Tabla resumen que ordena las técnicas por calidad y muestra el costo "
        "asociado. Útil para argumentar trade-offs en la sección de discusión."
    )
    lines.append("")
    # Para calidad/precisión usamos mean (distribución acotada). Para latencia
    # usamos p50 (la distribución es de cola larga por el cold-start de la
    # primera query del proceso warm; el mean sobreestima la latencia
    # steady-state).
    lines.append("| Rank | Técnica | mean_grade@10 (mean) | P@5 (mean) | latencia p50 (ms) |")
    lines.append("|---:|---|---:|---:|---:|")
    ranked = sorted(
        global_agg.items(),
        key=lambda kv: -(kv[1]["mean_grade_10"]["mean"] or 0),
    )
    for i, (tech, stats) in enumerate(ranked, 1):
        lines.append(
            f"| {i} | `{tech}` | {_fmt(stats['mean_grade_10']['mean'])} | "
            f"{_fmt(stats['p_at_5']['mean'])} | "
            f"{_fmt_ms(stats['lat_ms']['p50'])} |"
        )
    lines.append("")

    return "\n".join(lines) + "\n"


def _delta_safe(a: float | None, b: float | None) -> float | None:
    """Devuelve `b - a` redondeado, o None si alguno es None."""
    if a is None or b is None:
        return None
    return round(b - a, 3)


def _cross_k_h2h_table(
    sparse_agg: dict,
    hybrid_agg: dict,
    sparse_partners: list[str],
    metric_prefix: str,
    formatter,
) -> str:
    """Tabla head-to-head sparse vs híbrido a lo largo de los k de K_VALUES_REPORT.

    Columnas: para cada k, tres celdas (`sparse@k`, `híbrido@k`, `Δ@k`).
    Permite ver de un vistazo dónde el híbrido ayuda más (típicamente
    top-1/3 donde la fusión hace bubble-up de chunks semánticos) vs
    donde el sparse ya cubre bien (top-10).

    `metric_prefix` es `mean_grade` o `p_at`.
    """
    header_cells: list[str] = ["Sparse partner"]
    for k in K_VALUES_REPORT:
        header_cells.extend([f"sparse @{k}", f"híbrido @{k}", f"Δ @{k}"])
    align_cells = ["---"] + ["---:"] * (len(header_cells) - 1)
    lines = ["| " + " | ".join(header_cells) + " |", "|" + "|".join(align_cells) + "|"]

    for sk in sparse_partners:
        hk = f"{HYBRID_PREFIX}{sk}"
        if sk not in sparse_agg or hk not in hybrid_agg:
            continue
        row = [f"`{sk}`"]
        for k in K_VALUES_REPORT:
            mkey = f"{metric_prefix}_{k}"
            s_val = sparse_agg[sk][mkey]["mean"]
            h_val = hybrid_agg[hk][mkey]["mean"]
            row.extend([formatter(s_val), formatter(h_val), formatter(_delta_safe(s_val, h_val))])
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_comparative_report(
    evaluations: list[dict],
    judge_model: str | None = None,
) -> str:
    """Head-to-head sparse vs híbrido + ranking global mezclado.

    Cuatro secciones:

      1. **Head-to-head mean_grade cross-k**: para cada sparse partner,
         comparación de la calidad cross-query en top-1, top-3, top-5
         y top-10. Es la métrica principal de la tesis.

      2. **Head-to-head P@k cross-k**: misma forma, pero con la precisión
         de chunks altamente relevantes (grado=3 estricto).

      3. **Head-to-head latencia**: sparse vs híbrido (p50, p95) en ms.

      4. **Ranking global mezclado** + **cuándo gana híbrido**: las 16
         técnicas ordenadas por calidad y una vista por-query de qué tan
         seguido la fusión ayuda.
    """
    if not evaluations:
        return "# Reporte comparativo · sparse vs híbrido\n\nSin queries evaluadas.\n"

    sparse_agg = aggregate(evaluations, tech_filter=lambda t: not is_hybrid(t))
    hybrid_agg = aggregate(evaluations, tech_filter=is_hybrid)
    all_agg = aggregate(evaluations)

    lines: list[str] = []
    lines.append("# Reporte comparativo · sparse vs híbrido RRF")
    lines.append("")
    lines.append(f"**Queries evaluadas**: {len(evaluations)}")
    if judge_model:
        lines.append(f"**Modelo juez (LLM)**: `{judge_model}`")
    lines.append("**Híbrido**: fusión RRF (k=60) del ranking denso (Gemini en Qdrant)")
    lines.append("con cada uno de los 8 sparse partners.")
    lines.append("")
    lines.append(
        "Las métricas se reportan a varios k (1, 3, 5, 10) porque el "
        "comportamiento de la fusión RRF cambia con la profundidad: a top-1 "
        "el sparse suele dominar si la query es claramente léxica, y la "
        "fusión recupera terreno desde top-3 en adelante cuando entran "
        "chunks semánticos del lado denso."
    )
    lines.append("")

    # Iteramos sobre los sparse partners en el orden canónico (sorted) y solo
    # los que existen en AMBOS lados de la fusión.
    sparse_keys_in_pairs = sorted(
        k for k in sparse_agg if k in {sparse_partner_of(h) for h in hybrid_agg}
    )

    # --- 1. Head-to-head: mean_grade cross-k -------------------------------
    lines.append("## Head-to-head: `mean_grade` cross-k")
    lines.append("")
    lines.append(
        "Promedio cross-query de la relevancia (escala 0-3) en top-k. "
        "Δ = híbrido − sparse; positivo significa que la fusión mejora."
    )
    lines.append("")
    lines.append(
        _cross_k_h2h_table(sparse_agg, hybrid_agg, sparse_keys_in_pairs, "mean_grade", _fmt)
    )
    lines.append("")

    # --- 2. Head-to-head: P@k cross-k --------------------------------------
    lines.append("## Head-to-head: `P@k` cross-k (umbral estricto, grado=3)")
    lines.append("")
    lines.append(
        "Fracción de los primeros k chunks que el juez consideró *altamente "
        "relevantes* (grado 3). Métrica más estricta que mean_grade."
    )
    lines.append("")
    lines.append(_cross_k_h2h_table(sparse_agg, hybrid_agg, sparse_keys_in_pairs, "p_at", _fmt))
    lines.append("")

    # --- 3. Head-to-head: latencia -----------------------------------------
    lines.append("## Head-to-head: latencia (p50, p95)")
    lines.append("")
    lines.append(
        "p50 refleja el steady-state (no contaminado por el cold-start de "
        "la primera query del proceso warm). p95 da una idea del peor caso "
        "razonable. El híbrido siempre paga el costo de OpenSearch + Qdrant "
        "+ fusión, así que su latencia es necesariamente mayor."
    )
    lines.append("")
    lines.append(
        "| Sparse partner | sparse p50 (ms) | híbrido p50 (ms) | Δ p50 "
        "| sparse p95 (ms) | híbrido p95 (ms) | Δ p95 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for sk in sparse_keys_in_pairs:
        hk = f"{HYBRID_PREFIX}{sk}"
        if hk not in hybrid_agg:
            continue
        s_lat = sparse_agg[sk]["lat_ms"]
        h_lat = hybrid_agg[hk]["lat_ms"]
        lines.append(
            f"| `{sk}` | {_fmt_ms(s_lat['p50'])} | {_fmt_ms(h_lat['p50'])} | "
            f"{_fmt_ms(_delta_safe(s_lat['p50'], h_lat['p50']))} | "
            f"{_fmt_ms(s_lat['p95'])} | {_fmt_ms(h_lat['p95'])} | "
            f"{_fmt_ms(_delta_safe(s_lat['p95'], h_lat['p95']))} |"
        )
    lines.append("")

    # --- 4. Ranking global mezclado ----------------------------------------
    lines.append("## Ranking global (sparse + híbrido mezclados)")
    lines.append("")
    lines.append(
        "Las 16 técnicas ordenadas por `mean_grade@10` cross-query. "
        "Permite ver de un vistazo qué porcentaje del top-N son híbridos."
    )
    lines.append("")
    lines.append("| Rank | Técnica | Familia | mean_grade@10 | P@5 | lat p50 (ms) |")
    lines.append("|---:|---|---|---:|---:|---:|")
    ranked = sorted(
        all_agg.items(),
        key=lambda kv: -(kv[1]["mean_grade_10"]["mean"] or 0),
    )
    for i, (tech, stats) in enumerate(ranked, 1):
        family = "híbrido" if is_hybrid(tech) else "sparse"
        lines.append(
            f"| {i} | `{tech}` | {family} | "
            f"{_fmt(stats['mean_grade_10']['mean'])} | "
            f"{_fmt(stats['p_at_5']['mean'])} | "
            f"{_fmt_ms(stats['lat_ms']['p50'])} |"
        )
    lines.append("")

    # --- 5. Cuándo gana híbrido --------------------------------------------
    # Por cada query, contar cuántos pares (sparse, hybrid) el híbrido gana.
    lines.append("## Cuándo gana el híbrido")
    lines.append("")
    lines.append(
        "Por query y por par sparse↔híbrido, contamos 1 victoria si "
        "`rrf_X` tiene mejor `mean_grade@10` que `X` en esa query. "
        "El score por query es la tasa de victorias del híbrido (0-1) "
        "sobre los pares con ambos lados disponibles."
    )
    lines.append("")

    rows: list[tuple[str, float, int, int]] = []
    for ev in evaluations:
        metrics = ev.get("metrics", {})
        wins = 0
        total = 0
        for sk in sparse_keys_in_pairs:
            hk = f"{HYBRID_PREFIX}{sk}"
            s_score = metrics.get(sk, {}).get("top_10", {}).get("mean_grade")
            h_score = metrics.get(hk, {}).get("top_10", {}).get("mean_grade")
            if s_score is None or h_score is None:
                continue
            total += 1
            if h_score > s_score:
                wins += 1
        if total > 0:
            rows.append((ev["query_id"], wins / total, wins, total))

    rows.sort(key=lambda r: -r[1])
    lines.append("| Query | Tasa victorias híbrido | Victorias / Total pares |")
    lines.append("|---|---:|---:|")
    for qid, rate, wins, total in rows:
        lines.append(f"| `{qid}` | {rate:.2f} | {wins} / {total} |")
    lines.append("")

    if rows:
        overall_rate = sum(r[2] for r in rows) / sum(r[3] for r in rows)
        lines.append(f"**Tasa global de victorias del híbrido**: {overall_rate:.2%}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(
    evaluations_dir: Path,
    queries_dir: Path | None,
    output_dir: Path,
    judge_model: str | None,
) -> None:
    if not evaluations_dir.is_dir():
        sys.exit(f"[x] no existe {evaluations_dir}")

    evaluations = load_evaluations(evaluations_dir, queries_dir)
    if not evaluations:
        sys.exit(
            f"[x] no hay archivos qNNN_eval.json en {evaluations_dir}. "
            "Corra primero scripts/benchmark/evaluate_query.py."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Reporte 1: sparse-only
    sparse_path = output_dir / "reporte_sparse.md"
    sparse_path.write_text(
        build_report(
            evaluations,
            title="Reporte sparse del benchmark",
            subtitle=(
                "Las 8 técnicas esparsas (P1/P2/P3 × BM25/TF-IDF + SPLADE + "
                "baseline_qdrant_bm25), aisladas del componente denso."
            ),
            tech_filter=lambda t: not is_hybrid(t),
            judge_model=judge_model,
        )
    )

    # Reporte 2: hybrid-only
    hybrid_path = output_dir / "reporte_hibrido.md"
    hybrid_path.write_text(
        build_report(
            evaluations,
            title="Reporte híbrido (RRF) del benchmark",
            subtitle=(
                "Los 8 combos `rrf_<sparse>`: fusión Reciprocal Rank Fusion "
                "(k=60) del ranking denso Gemini con cada sparse partner."
            ),
            tech_filter=is_hybrid,
            judge_model=judge_model,
        )
    )

    # Reporte 3: comparativo
    comparative_path = output_dir / "reporte_comparativo.md"
    comparative_path.write_text(build_comparative_report(evaluations, judge_model=judge_model))

    print(f"[+] reportes en {output_dir}/:")
    print(f"      · {sparse_path.name}")
    print(f"      · {hybrid_path.name}")
    print(f"      · {comparative_path.name}")
    print(f"    queries evaluadas: {len(evaluations)}")
    temas = sorted({ev["_tema"] for ev in evaluations})
    print(f"    temas representados: {len(temas)}")
    for t in temas:
        n = sum(1 for ev in evaluations if ev["_tema"] == t)
        print(f"      · {t}: {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evaluations-dir",
        type=Path,
        default=Path("scripts/benchmark/evaluations"),
    )
    parser.add_argument(
        "--queries-dir",
        type=Path,
        default=Path("scripts/benchmark/queries"),
        help=(
            "Carpeta con los JSON de queries. Se usa solo para leer el "
            "campo opcional `tema` si está presente; si no, los temas se "
            "infieren del rango de query_id."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scripts/benchmark"),
        help="Carpeta donde escribir los 3 reportes (reporte_sparse.md, etc.).",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Modelo del juez LLM usado (se incluye en el header de los reportes).",
    )
    args = parser.parse_args()

    main(
        evaluations_dir=args.evaluations_dir,
        queries_dir=args.queries_dir,
        output_dir=args.output_dir,
        judge_model=args.judge_model,
    )
