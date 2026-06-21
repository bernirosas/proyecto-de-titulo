"""Tests de las funciones puras del pipeline de benchmarking.

Selección deliberada de tests con valor real de detección:

  - `_strip_markdown_fences` en judge_pool.py: si falla, todos los
    judgments quedan marcados con relevance_grade=-1 (PARSE_ERROR) y
    se contamina el ground truth. Tiene casos borde reales (Gemini a
    veces envuelve la respuesta en ```json, a veces en ```, a veces sin
    cierre, a veces con espacios).

  - `build_summary` en ingest_judgments.py: si falla, el reporte
    consolidado de la tesis arroja números incorrectos. Es una función
    pura que agrega los judgments, vale la pena verificar que las
    cuentas (distribución de grados, fallidos, promedio por query)
    se calculen bien.

Se omiten deliberadamente:

  - `retrieve_for_query.retrieve_all_sparse`, `hydrate_pool`,
    `index_rankings_in_opensearch`: todas talkean a OpenSearch directo.
    Mockearlas testearía el mock, no el comportamiento real.
  - La deduplicación inline del pool: cuatro líneas que esencialmente
    testean `set.add` y `list.append` de Python.
  - El prompt template: testear su contenido sería tautológico
    (verificar que la string contiene los strings que pusimos).
  - `judge_chunk`: orquesta Gemini. La parte de parsing está cubierta
    por los tests de `_strip_markdown_fences`.
"""

from __future__ import annotations

from evaluate_query import (
    RELEVANCE_THRESHOLD,
    _latency_ms,
    evaluate_ranking,
    format_table,
    identify_winner,
)
from ingest_judgments import build_summary
from judge_pool import PROMPT_TEMPLATE, _strip_markdown_fences

# ---------------------------------------------------------------------------
# _strip_markdown_fences
# ---------------------------------------------------------------------------


class TestStripMarkdownFences:
    def test_no_fences_passes_through(self):
        """Si Gemini devuelve JSON limpio, la función no debe modificarlo."""
        s = '{"relevance_grade": 2, "justification": "OK"}'
        assert _strip_markdown_fences(s) == s

    def test_json_fence_with_label_stripped(self):
        """El caso más frecuente: Gemini envuelve la respuesta en ```json ... ```"""
        s = '```json\n{"relevance_grade": 2}\n```'
        assert _strip_markdown_fences(s) == '{"relevance_grade": 2}'

    def test_bare_fence_without_language_stripped(self):
        """Variante sin la etiqueta `json` después de los backticks."""
        s = '```\n{"relevance_grade": 3}\n```'
        assert _strip_markdown_fences(s) == '{"relevance_grade": 3}'

    def test_leading_trailing_whitespace_trimmed(self):
        """Espacios y saltos de línea sobrantes no deben romper el parser."""
        s = '   {"relevance_grade": 2}   \n'
        assert _strip_markdown_fences(s) == '{"relevance_grade": 2}'

    def test_fence_without_closing_keeps_content(self):
        """Si Gemini truncó la respuesta (rate limit, max_tokens), no fallar:
        devolver lo que haya después del ``` inicial para que el JSON.loads
        intente parsear con un mensaje de error claro, no un crash."""
        s = '```json\n{"relevance_grade": 2'
        assert _strip_markdown_fences(s) == '{"relevance_grade": 2'

    def test_empty_string(self):
        """Edge case: respuesta vacía."""
        assert _strip_markdown_fences("") == ""


# ---------------------------------------------------------------------------
# PROMPT_TEMPLATE
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_format_does_not_raise(self):
        """Regresión: si alguien edita el prompt y deja una llave `{` o `}`
        sin escapar (debería ser `{{` o `}}`), `str.format` interpreta el
        contenido como un placeholder con nombre y crashea con KeyError.
        Este test ejecuta el format con los argumentos esperados; cualquier
        llave mal escapada lo hace fallar en CI antes que en producción."""
        # No verificamos el contenido — eso sería tautológico. Solo que
        # el format no levante excepción.
        result = PROMPT_TEMPLATE.format(
            query="consulta de prueba",
            name="Documento de prueba",
            source_type="ley",
            content='Contenido de prueba con caracteres especiales: {} "texto".',
        )
        # Sanity: los placeholders deben haber sido reemplazados.
        assert "consulta de prueba" in result
        assert "Documento de prueba" in result
        # Los ejemplos en el prompt (que tienen `{` y `}` escapados) deben
        # haberse resuelto a llaves literales.
        assert '{"justification"' in result
        assert '"relevance_grade": 3}' in result


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_empty_rows_produces_zero_counts(self):
        """Sin judgments cargados, el resumen debe ser todo ceros sin crash."""
        summary = build_summary([])
        assert summary["queries_evaluadas"] == 0
        assert summary["judgments_totales"] == 0
        assert summary["judgments_fallidos_parse"] == 0
        assert summary["distribucion_de_grados"] == {"0": 0, "1": 0, "2": 0, "3": 0}
        assert summary["por_query"] == {}

    def test_grade_distribution_counted_correctly(self):
        """Cuenta básica de grados (0, 1, 2, 3) por su frecuencia."""
        rows = [
            {"query_id": "q001", "relevance_grade": 3},
            {"query_id": "q001", "relevance_grade": 3},
            {"query_id": "q001", "relevance_grade": 2},
            {"query_id": "q001", "relevance_grade": 0},
        ]
        summary = build_summary(rows)
        assert summary["distribucion_de_grados"] == {
            "0": 1,
            "1": 0,
            "2": 1,
            "3": 2,
        }

    def test_failed_judgments_excluded_from_distribution(self):
        """Los judgments con grade=-1 (PARSE_ERROR) se cuentan aparte y no
        contaminan la distribución de grados ni el promedio por query."""
        rows = [
            {"query_id": "q001", "relevance_grade": 3},
            {"query_id": "q001", "relevance_grade": -1},
            {"query_id": "q001", "relevance_grade": -1},
        ]
        summary = build_summary(rows)
        assert summary["judgments_fallidos_parse"] == 2
        assert summary["distribucion_de_grados"]["3"] == 1
        # Solo el grade=3 entró al promedio.
        assert summary["por_query"]["q001"]["n_judgments"] == 1
        assert summary["por_query"]["q001"]["grade_mean"] == 3.0

    def test_per_query_breakdown(self):
        """Una fila por query con su n_judgments, grade_mean y n_relevantes_2_o_3."""
        rows = [
            {"query_id": "q001", "relevance_grade": 3},
            {"query_id": "q001", "relevance_grade": 2},
            {"query_id": "q001", "relevance_grade": 0},
            {"query_id": "q002", "relevance_grade": 1},
            {"query_id": "q002", "relevance_grade": 1},
        ]
        summary = build_summary(rows)
        assert summary["queries_evaluadas"] == 2
        assert summary["por_query"]["q001"] == {
            "n_judgments": 3,
            "grade_mean": round((3 + 2 + 0) / 3, 3),
            "n_relevantes_2_o_3": 2,
        }
        assert summary["por_query"]["q002"] == {
            "n_judgments": 2,
            "grade_mean": 1.0,
            "n_relevantes_2_o_3": 0,
        }

    def test_judgments_totales_excludes_failed(self):
        """`judgments_totales` cuenta solamente las filas válidas (grade != -1)."""
        rows = [
            {"query_id": "q001", "relevance_grade": 3},
            {"query_id": "q001", "relevance_grade": -1},
            {"query_id": "q002", "relevance_grade": 0},
        ]
        summary = build_summary(rows)
        assert summary["judgments_totales"] == 2
        assert summary["judgments_fallidos_parse"] == 1


# ---------------------------------------------------------------------------
# evaluate_query.evaluate_ranking
# ---------------------------------------------------------------------------


class TestEvaluateRanking:
    def test_relevance_threshold_is_strict_grade_3(self):
        """Decisión de diseño explícita: P@k cuenta solamente grado 3.
        Si alguien la cambia, este test falla y obliga a actualizarlo."""
        assert RELEVANCE_THRESHOLD == 3

    def test_basic_mean_and_precision(self):
        """Mean es el promedio de los grados; P@k es la fracción con grado >= 3."""
        ranking = [
            {"chunk_uuid": "a", "rank": 1, "score": 10.0},
            {"chunk_uuid": "b", "rank": 2, "score": 8.0},
            {"chunk_uuid": "c", "rank": 3, "score": 6.0},
        ]
        # grados 3, 2, 1 → mean=2.0, P@3=1/3 (solo "a" es 3)
        judgments = {"a": 3, "b": 2, "c": 1}
        m = evaluate_ranking(ranking, judgments, k=3)
        assert m["mean_grade"] == 2.0
        assert m["precision_at_k"] == round(1 / 3, 3)
        assert m["n_judged"] == 3

    def test_skips_failed_judgments(self):
        """Chunks con grade=-1 (PARSE_ERROR) se omiten del mean y de P@k."""
        ranking = [
            {"chunk_uuid": "a", "rank": 1, "score": 10.0},
            {"chunk_uuid": "b", "rank": 2, "score": 8.0},
        ]
        judgments = {"a": 3, "b": -1}
        m = evaluate_ranking(ranking, judgments, k=2)
        assert m["mean_grade"] == 3.0
        assert m["precision_at_k"] == 1.0  # 1 de 1 chunks juzgados es grado 3
        assert m["n_failed"] == 1
        assert m["n_judged"] == 1

    def test_missing_judgment_counted_separately(self):
        """Chunks sin entry en judgments se cuentan como n_missing, no como 0."""
        ranking = [{"chunk_uuid": "a", "rank": 1, "score": 10}]
        m = evaluate_ranking(ranking, {}, k=1)
        assert m["mean_grade"] is None  # explícito, no 0
        assert m["precision_at_k"] is None
        assert m["n_missing"] == 1
        assert m["n_judged"] == 0

    def test_k_larger_than_ranking_uses_what_exists(self):
        """Si k=10 pero el ranking solo tiene 3 chunks, evalúa los 3."""
        ranking = [{"chunk_uuid": "a", "rank": 1, "score": 10}]
        m = evaluate_ranking(ranking, {"a": 2}, k=10)
        assert m["mean_grade"] == 2.0
        assert m["precision_at_k"] == 0.0  # grado 2 < umbral 3
        assert m["n_judged"] == 1


# ---------------------------------------------------------------------------
# evaluate_query.identify_winner
# ---------------------------------------------------------------------------


class TestIdentifyWinner:
    def test_picks_highest_mean_at_top_10(self):
        metrics = {
            "p1_bm25": {"top_10": {"mean_grade": 1.5}},
            "p1_splade": {"top_10": {"mean_grade": 2.3}},
            "p2_tfidf": {"top_10": {"mean_grade": 1.8}},
        }
        winner, score = identify_winner(metrics)
        assert winner == "p1_splade"
        assert score == 2.3

    def test_handles_all_none(self):
        """Si todas las técnicas tienen top-10 sin judgments, no hay ganador."""
        metrics = {
            "p1_bm25": {"top_10": {"mean_grade": None}},
            "p1_splade": {"top_10": {"mean_grade": None}},
        }
        winner, score = identify_winner(metrics)
        assert winner is None
        assert score is None


# ---------------------------------------------------------------------------
# evaluate_query._latency_ms: tolerancia a shapes mixtos del pool JSON
# ---------------------------------------------------------------------------


class TestLatencyMs:
    def test_missing_technique_returns_none(self):
        """Si la técnica no está en el dict (o el dict es None), debe
        devolver None para que la tabla muestre guión, no un falso cero."""
        assert _latency_ms(None, "p1_bm25") is None
        assert _latency_ms({"p3_bm25": 12.0}, "p1_bm25") is None

    def test_float_shape_returns_float(self):
        """Shape canónico que produce retrieve_for_query.py:
        `{tecnica: float_ms}`."""
        assert _latency_ms({"p1_bm25": 42.5}, "p1_bm25") == 42.5

    def test_dict_shape_extracts_mean(self):
        """Backward-compat: pools generados con experimentación de
        agregación estadística traían `{tecnica: {mean, p50, p95, n}}`.
        Se extrae mean para preservar legibilidad de la columna."""
        latencies = {"p1_bm25": {"mean": 12.3, "p50": 11.8, "p95": 18.4, "n": 5}}
        assert _latency_ms(latencies, "p1_bm25") == 12.3


# ---------------------------------------------------------------------------
# evaluate_query.format_table: columna lat ms se incluye y se omite con None
# ---------------------------------------------------------------------------


class TestFormatTable:
    def _minimal_metrics(self) -> dict:
        """Métricas mínimas para una sola técnica, todos los top_k poblados."""
        cell = {
            "mean_grade": 2.0,
            "precision_at_k": 0.5,
            "n_judged": 5,
            "n_missing": 0,
            "n_failed": 0,
        }
        return {"p1_bm25": {f"top_{k}": cell for k in (1, 3, 5, 10)}}

    def test_header_always_includes_latency_column(self):
        """La tabla siempre incluye la columna 'lat ms', aun cuando no
        se pasa el dict de latencias (caso pool legacy sin medición)."""
        out = format_table(self._minimal_metrics())
        assert "lat ms" in out

    def test_latency_dashed_when_missing(self):
        """Si el pool no tiene latencia para una técnica, la columna
        sale con guión — nunca con un cero engañoso."""
        out = format_table(self._minimal_metrics(), latencies=None)
        body_line = [ln for ln in out.splitlines() if "p1_bm25" in ln][0]
        assert body_line.rstrip().endswith("—")

    def test_latency_shown_when_present(self):
        """Si el pool trae la latencia, se muestra en ms con un decimal."""
        out = format_table(self._minimal_metrics(), latencies={"p1_bm25": 12.3})
        assert "12.3" in out
