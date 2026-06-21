"""Tests de las funciones puras del consolidador cross-query.

`consolidate_evaluations.py` produce el Markdown final que alimenta la
sección de resultados de la tesis. Sus funciones helper son puras (sin
I/O, sin red, sin sistema), así que son baratas y útiles de testear.

Cubrimos:
  - `_tema_for`: asignación de tema por rango + override por campo
    opcional del query JSON.
  - `_stats`: mean / p50 / p95 sobre samples, incluido el caso vacío.
  - `_latency_of`: tolerancia a los dos shapes que pueden venir en los
    pools (float crudo o dict con campo 'mean').
  - `_winner_of`: técnica con mayor mean_grade@10 cross-query.
  - `aggregate`: agregación cross-query a partir de la lista de
    evaluaciones cargadas.

Lo que se omite:
  - I/O sobre archivos (`load_evaluations`, `main`, `build_report`):
    requiere fixtures de filesystem que costaría más mantener que la
    señal experimental que dan.
  - Formato Markdown exacto (`_technique_table`, `build_report`): es
    presentation-layer, los tests se vuelven tautológicos (verifican
    que el output contiene los strings que pusimos).
"""

from __future__ import annotations

from consolidate_evaluations import (
    TEMA_SEED,
    _latency_of,
    _stats,
    _tema_for,
    _winner_of,
    aggregate,
)

# ---------------------------------------------------------------------------
# _tema_for
# ---------------------------------------------------------------------------


class TestTemaFor:
    def test_query_in_arrendamientos_range(self):
        """q001-q005 cae en Arrendamientos según TEMA_RANGES."""
        assert _tema_for("q001") == "Arrendamientos"
        assert _tema_for("q005") == "Arrendamientos"

    def test_query_in_jurisprudencia_range(self):
        """q026-q030 cae en Jurisprudencia de inmuebles."""
        assert _tema_for("q026") == "Jurisprudencia de inmuebles"
        assert _tema_for("q030") == "Jurisprudencia de inmuebles"

    def test_query_outside_ranges_is_seed(self):
        """q000 y queries fuera de los rangos definidos caen como sanity check."""
        assert _tema_for("q000") == TEMA_SEED
        assert _tema_for("q999") == TEMA_SEED

    def test_explicit_override_takes_priority(self):
        """El campo `tema` del JSON pisa la asignación por rango. Esto
        permite al equipo redefinir manualmente la asignación de una
        query sin tener que editar TEMA_RANGES."""
        assert _tema_for("q001", override="Custom Topic") == "Custom Topic"

    def test_unparseable_id_falls_back_to_seed(self):
        """Si el query_id no calza con `q<entero>`, no truena: cae al
        seed. Robustez ante IDs malformados sin abortar el reporte."""
        assert _tema_for("not_a_query_id") == TEMA_SEED
        assert _tema_for("qabc") == TEMA_SEED


# ---------------------------------------------------------------------------
# _stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_empty_samples(self):
        """Sin samples, todos los campos son None y n=0. Defensa para
        técnicas que no devolvieron data juzgable en ninguna query del
        conjunto agregado."""
        result = _stats([])
        assert result == {"mean": None, "p50": None, "p95": None, "n": 0}

    def test_single_sample(self):
        """Con n=1, mean = p50 = p95 = el valor único. Preserva forma
        uniforme del dict; el consumidor no ramifica."""
        result = _stats([42.0])
        assert result["n"] == 1
        assert result["mean"] == 42.0
        assert result["p50"] == 42.0
        assert result["p95"] == 42.0

    def test_basic_mean_and_median(self):
        """Cinco valores ordenados, mean y mediana clásicos."""
        result = _stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["n"] == 5
        assert result["mean"] == 3.0
        assert result["p50"] == 3.0
        # p95 con n=5: ceil(5*0.95) - 1 = índice 4 (último) = 5.0
        assert result["p95"] == 5.0

    def test_p95_robust_to_central_outlier(self):
        """Con 20 valores y un único outlier alto, p95 captura el outlier
        mientras p50 mantiene la mediana del cuerpo. Esto justifica
        reportar las tres estadísticas: una sola engaña."""
        samples = [10.0] * 19 + [1000.0]
        result = _stats(samples)
        assert result["p50"] == 10.0
        # mean cae entre los dos
        assert 10.0 < result["mean"] < 1000.0


# ---------------------------------------------------------------------------
# _latency_of
# ---------------------------------------------------------------------------


class TestLatencyOf:
    def test_missing_latencies_dict_returns_none(self):
        """Pool sin clave 'latencies': la técnica no tiene latencia
        registrada → None. No truena."""
        assert _latency_of({}, "p1_bm25") is None
        assert _latency_of({"latencies": None}, "p1_bm25") is None

    def test_float_shape_returns_float(self):
        """Shape canónico que produce `retrieve_for_query.py`:
        `{tecnica: float_ms}`."""
        eval_data = {"latencies": {"p1_bm25": 12.5}}
        assert _latency_of(eval_data, "p1_bm25") == 12.5

    def test_dict_shape_extracts_mean(self):
        """Backward-compat con pools generados con agregación estadística
        experimental: el dict trae `{mean, p50, p95, n}`, se extrae mean
        para el reporte unificado."""
        eval_data = {"latencies": {"p1_bm25": {"mean": 15.3, "p50": 14.0, "p95": 22.0, "n": 5}}}
        assert _latency_of(eval_data, "p1_bm25") == 15.3

    def test_dict_shape_without_mean_returns_none(self):
        """Defensa: dict legacy sin campo 'mean' no debería existir,
        pero si aparece devolvemos None en vez de explotar."""
        eval_data = {"latencies": {"p1_bm25": {"p50": 14.0}}}
        assert _latency_of(eval_data, "p1_bm25") is None

    def test_technique_not_in_latencies(self):
        """Técnica ausente del dict de latencias → None (no KeyError)."""
        eval_data = {"latencies": {"p3_bm25": 8.0}}
        assert _latency_of(eval_data, "p1_bm25") is None


# ---------------------------------------------------------------------------
# _winner_of
# ---------------------------------------------------------------------------


class TestWinnerOf:
    def test_picks_highest_mean_grade(self):
        """La técnica con mayor mean(mean_grade@10) cross-query gana."""
        agg = {
            "p3_bm25": {"mean_grade_10": {"mean": 2.10, "p50": 2.0, "p95": 2.4, "n": 5}},
            "p1_splade": {"mean_grade_10": {"mean": 1.85, "p50": 1.9, "p95": 2.3, "n": 5}},
            "baseline_qdrant_bm25": {
                "mean_grade_10": {"mean": 1.70, "p50": 1.8, "p95": 2.5, "n": 5}
            },
        }
        winner, score = _winner_of(agg)
        assert winner == "p3_bm25"
        assert score == 2.10

    def test_all_none_returns_none(self):
        """Si ninguna técnica tiene mean válido (corrida sin judgments),
        no hay ganador. Reporte transparente."""
        agg = {
            "p1_bm25": {"mean_grade_10": {"mean": None, "p50": None, "p95": None, "n": 0}},
        }
        winner, score = _winner_of(agg)
        assert winner is None
        assert score is None

    def test_ignores_techniques_with_none_mean(self):
        """Si una técnica está sin data (None) pero otras sí, gana la
        mejor entre las que tienen data — no truena por la None."""
        agg = {
            "p3_bm25": {"mean_grade_10": {"mean": 2.0, "p50": 2.0, "p95": 2.3, "n": 5}},
            "splade_broken": {"mean_grade_10": {"mean": None, "p50": None, "p95": None, "n": 0}},
        }
        winner, score = _winner_of(agg)
        assert winner == "p3_bm25"
        assert score == 2.0


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_empty_evaluations(self):
        """Lista vacía produce dict vacío. No truena."""
        result = aggregate([])
        assert result == {}

    def test_single_evaluation_produces_stats(self):
        """Con una sola evaluación, las estadísticas reportan mean = p50
        = p95 = el valor único de esa query."""
        evaluations = [
            {
                "metrics": {
                    "p3_bm25": {
                        "top_10": {"mean_grade": 2.5, "precision_at_k": 0.6},
                        "top_5": {"mean_grade": 2.6, "precision_at_k": 0.7},
                    }
                },
                "latencies": {"p3_bm25": 12.0},
            }
        ]
        result = aggregate(evaluations)
        assert "p3_bm25" in result
        stats = result["p3_bm25"]
        assert stats["mean_grade_10"]["mean"] == 2.5
        assert stats["p_at_5"]["mean"] == 0.7
        assert stats["lat_ms"]["mean"] == 12.0

    def test_multiple_evaluations_average_correctly(self):
        """Dos evaluaciones de la misma técnica: el mean es el promedio
        de los dos valores de mean_grade@10."""
        evaluations = [
            {
                "metrics": {
                    "p3_bm25": {
                        "top_10": {"mean_grade": 2.0, "precision_at_k": 0.4},
                        "top_5": {"mean_grade": 2.0, "precision_at_k": 0.4},
                    }
                },
                "latencies": {"p3_bm25": 10.0},
            },
            {
                "metrics": {
                    "p3_bm25": {
                        "top_10": {"mean_grade": 3.0, "precision_at_k": 1.0},
                        "top_5": {"mean_grade": 3.0, "precision_at_k": 1.0},
                    }
                },
                "latencies": {"p3_bm25": 20.0},
            },
        ]
        result = aggregate(evaluations)
        assert result["p3_bm25"]["mean_grade_10"]["mean"] == 2.5  # (2.0 + 3.0) / 2
        assert result["p3_bm25"]["lat_ms"]["mean"] == 15.0  # (10 + 20) / 2

    def test_skips_none_metrics(self):
        """Una evaluación con mean_grade=None (todos los chunks sin
        judgment) no debe contribuir al promedio — se omite, no se
        cuenta como cero."""
        evaluations = [
            {
                "metrics": {
                    "p3_bm25": {
                        "top_10": {"mean_grade": 2.0, "precision_at_k": 0.4},
                        "top_5": {"mean_grade": 2.0, "precision_at_k": 0.4},
                    }
                },
                "latencies": {"p3_bm25": 10.0},
            },
            {
                "metrics": {
                    "p3_bm25": {
                        "top_10": {"mean_grade": None, "precision_at_k": None},
                        "top_5": {"mean_grade": None, "precision_at_k": None},
                    }
                },
                "latencies": {},
            },
        ]
        result = aggregate(evaluations)
        # Solo el primero contribuye al promedio.
        assert result["p3_bm25"]["mean_grade_10"]["mean"] == 2.0
        assert result["p3_bm25"]["mean_grade_10"]["n"] == 1
