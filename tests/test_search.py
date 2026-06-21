"""Tests de la lógica de construcción de queries en `src.search`.

Selección deliberada de tests con valor real de detección. Se eliminaron
los siguientes por considerarse tautológicos o de bajo valor:

  - Tests que solo verifican que un dict tiene las claves que el código
    pone (test_basic_match_query, test_returned_source_fields,
    test_minimum_should_match_one, los tres tests de _format_hits).
  - Duplicaciones del mismo edge case empty-tokens en BM25 / TFIDF /
    SPLADE: se conserva uno y los demás se eliminan.
  - Tests de normalización a minúscula y de errores triviales que se
    superponen entre sí.

Lo que se mantiene cubre tres tipos de falla con consecuencia real en
producción:

  1. Errores de tipeo en nombres de campo OpenSearch (un `tfidf_p1.x`
     mal escrito devuelve cero hits sin error).
  2. Confusión entre los contratos de TFIDF (boost por TF) y SPLADE
     (boost por peso del encoder).
  3. Violaciones de la restricción de OpenSearch que prohíbe valores
     ≤ 0 en `rank_features` — produce un 400 silencioso.
"""

from __future__ import annotations

import pytest
from src import config, search

# ---------------------------------------------------------------------------
# _split_method: catálogo y errores
# ---------------------------------------------------------------------------


class TestSplitMethod:
    def test_each_canonical_technique_in_catalog_parses(self):
        """Cada entrada canónica de config.TECHNIQUES debe dispatcharse
        correctamente. Las técnicas no-canónicas (`baseline_qdrant_bm25`,
        `hybrid_rrf`) se ramifican en `search()` antes de llegar a
        `_split_method`, así que se excluyen explícitamente acá."""
        non_canonical = {"baseline_qdrant_bm25", "hybrid_rrf"}
        for method in config.TECHNIQUES:
            if method in non_canonical:
                continue
            preproc, vec = search._split_method(method)
            assert preproc in {"p1", "p2", "p3"}
            assert vec in {"bm25", "tfidf", "splade"}

    def test_non_canonical_technique_raises(self):
        """Si una técnica no-canónica llega a `_split_method`, debe
        levantar ValueError: el caller (search) debió haber ramificado
        antes. Si este test rompe, es señal de que se agregó una técnica
        de formato libre sin ramificarla."""
        with pytest.raises(ValueError, match="no acepta técnicas no-canónicas"):
            search._split_method("baseline_qdrant_bm25")

    def test_invalid_method_raises_value_error(self):
        """Contrato de error: solicitudes con un método desconocido deben
        levantar ValueError (que la API traduce a HTTP 400)."""
        with pytest.raises(ValueError, match="Técnica desconocida"):
            search._split_method("p9_inexistente")


# ---------------------------------------------------------------------------
# _build_bm25_body: nombres de campo correctos y manejo de input vacío
# ---------------------------------------------------------------------------


class TestBuildBM25Body:
    def test_field_uses_preproc(self):
        """Detección de errata: el campo `content_pX` debe respetar el
        preprocesamiento solicitado. Una errata produce cero hits sin error."""
        body = search._build_bm25_body(["x"], preproc="p3", size=1, scoring="default")
        assert "content_p3" in body["query"]["match"]

    def test_empty_tokens_returns_match_none(self):
        """Si todos los tokens fueron filtrados (p. ej. solo stop words),
        OpenSearch debe recibir `match_none` en lugar de un match vacío,
        que en algunas versiones se interpreta como `match_all`."""
        body = search._build_bm25_body([], preproc="p1", size=5, scoring="default")
        assert body["query"] == {"match_none": {}}
        assert body["size"] == 0

    def test_default_variant_uses_base_field(self):
        """Variante `default`: el campo base `content_pX` (sin sufijo)."""
        body = search._build_bm25_body(["x"], preproc="p2", size=1, scoring="default")
        assert "content_p2" in body["query"]["match"]
        assert "content_p2_a" not in body["query"]["match"]

    def test_tuned_variants_use_sibling_fields(self):
        """Variantes `tuned_a/b/c`: el campo hermano con el sufijo correspondiente
        debe ser el target del `match` query. Un error acá implica que el
        scoring del usuario se aplica al campo equivocado y la comparación
        entre variantes se vuelve inválida."""
        for scoring, suffix in (("tuned_a", "_a"), ("tuned_b", "_b"), ("tuned_c", "_c")):
            body = search._build_bm25_body(["x"], preproc="p1", size=1, scoring=scoring)
            assert f"content_p1{suffix}" in body["query"]["match"]

    def test_unknown_bm25_variant_raises(self):
        """Variantes que no están en config.BM25_VARIANTS deben rechazarse
        con un mensaje accionable, no producir un campo inexistente con
        cero hits silenciosos."""
        with pytest.raises(ValueError, match="Variante de scoring BM25"):
            search._build_bm25_body(["x"], preproc="p1", size=1, scoring="tuned_z")


# ---------------------------------------------------------------------------
# _build_tfidf_body: contrato de boost = TF, scoring linear, nombre de campo
# ---------------------------------------------------------------------------


class TestBuildTfidfBody:
    def test_uses_tf_as_boost(self):
        """Contrato del scoring asimétrico TFIDF: el lado-query lleva la
        frecuencia bruta del término; el lado-documento ya integra IDF."""
        body = search._build_tfidf_body(
            ["iva", "iva", "fiscal"], preproc="p2", size=10, scoring="linear"
        )
        boosts = {
            clause["rank_feature"]["field"]: clause["rank_feature"]["boost"]
            for clause in body["query"]["bool"]["should"]
        }
        assert boosts["tfidf_p2.iva"] == 2.0
        assert boosts["tfidf_p2.fiscal"] == 1.0

    def test_field_includes_preproc_and_token(self):
        """El path del rank_feature debe ser `tfidf_pX.<token>`. Una errata
        en el prefijo o en el separador produce cero matches sin error."""
        body = search._build_tfidf_body(["restitucion"], preproc="p3", size=1, scoring="linear")
        clause = body["query"]["bool"]["should"][0]
        assert clause["rank_feature"]["field"] == "tfidf_p3.restitucion"

    def test_linear_variant_emits_empty_linear_clause(self):
        """Variante `linear`: cada `rank_feature` lleva `linear: {}` sin
        parámetros. Distinguir esto de `saturation` permite verificar la
        elección de scoring del usuario."""
        body = search._build_tfidf_body(["x"], preproc="p1", size=1, scoring="linear")
        clause = body["query"]["bool"]["should"][0]
        assert "linear" in clause["rank_feature"]
        assert clause["rank_feature"]["linear"] == {}
        assert "saturation" not in clause["rank_feature"]

    def test_saturation_variants_include_pivot(self):
        """Variantes `saturation_pX`: cada `rank_feature` debe llevar
        `saturation` con su pivot correspondiente. Si el pivot no se
        propaga, OpenSearch usa el default (la media de la feature) y el
        usuario no obtiene el comportamiento que pidió."""
        cases = [
            ("saturation_p0_5", 0.5),
            ("saturation_p1", 1.0),
            ("saturation_p5", 5.0),
            ("saturation_p10", 10.0),
        ]
        for scoring, expected_pivot in cases:
            body = search._build_tfidf_body(["x"], preproc="p1", size=1, scoring=scoring)
            clause = body["query"]["bool"]["should"][0]["rank_feature"]
            assert "saturation" in clause
            assert clause["saturation"] == {"pivot": expected_pivot}
            assert "linear" not in clause

    def test_unknown_rank_feature_variant_raises(self):
        """Variantes que no están en config.RANK_FEATURE_VARIANTS deben
        rechazarse explícitamente."""
        with pytest.raises(ValueError, match="rank_feature desconocida"):
            search._build_tfidf_body(["x"], preproc="p1", size=1, scoring="saturation_p999")


# ---------------------------------------------------------------------------
# _build_splade_body: contrato distinto de TFIDF, filtros, WordPiece
# ---------------------------------------------------------------------------


class TestBuildSpladeBody:
    def test_uses_provided_weights_not_tf(self):
        """SPLADE difiere de TFIDF en el lado-query: el boost es el peso
        del encoder, no la frecuencia bruta. Confundirlos invalida el
        ranking porque el encoder ya pondera y expande léxicamente."""
        weights = {"##cion": 0.7, "noti": 1.5}
        body = search._build_splade_body(weights, preproc="p1", size=5, scoring="linear")
        boosts = {
            c["rank_feature"]["field"]: c["rank_feature"]["boost"]
            for c in body["query"]["bool"]["should"]
        }
        assert boosts["splade_p1.##cion"] == pytest.approx(0.7)
        assert boosts["splade_p1.noti"] == pytest.approx(1.5)

    def test_zero_or_negative_weights_filtered(self):
        """OpenSearch rechaza valores ≤ 0 en `rank_features` con un 400.
        Los tokens que SPLADE pondera en cero o negativo se filtran del
        cuerpo de la consulta."""
        weights = {"a": 0.5, "b": 0.0, "c": -0.1, "d": 2.0}
        body = search._build_splade_body(weights, preproc="p1", size=5, scoring="linear")
        fields = [c["rank_feature"]["field"] for c in body["query"]["bool"]["should"]]
        assert "splade_p1.a" in fields
        assert "splade_p1.d" in fields
        assert "splade_p1.b" not in fields
        assert "splade_p1.c" not in fields

    def test_preserves_wordpiece_prefixes(self):
        """Los tokens con prefijo `##` corresponden a piezas de continuación
        del tokenizer WordPiece de BERT; sanitizarlos produce mismatch
        contra los vectores indexados."""
        body = search._build_splade_body({"##og": 1.0}, preproc="p1", size=1, scoring="linear")
        clause = body["query"]["bool"]["should"][0]
        assert clause["rank_feature"]["field"] == "splade_p1.##og"

    def test_splade_applies_saturation_variant(self):
        """Verificación cruzada: SPLADE comparte el dict RANK_FEATURE_VARIANTS
        con TF-IDF, así que cualquier saturación debe propagarse igual."""
        body = search._build_splade_body({"a": 1.0}, preproc="p1", size=1, scoring="saturation_p5")
        clause = body["query"]["bool"]["should"][0]["rank_feature"]
        assert clause["saturation"] == {"pivot": 5.0}


# ---------------------------------------------------------------------------
# _build_baseline_qdrant_bm25_body: campo fijo, claves hash, filtros
# ---------------------------------------------------------------------------


class TestBuildBaselineQdrantBM25Body:
    def test_field_is_baseline_qdrant_bm25(self):
        """A diferencia de TFIDF/SPLADE el campo no depende del preproc:
        la baseline tiene un único campo `baseline_qdrant_bm25.<hash>` para
        todos los chunks. Si esto cambia, los queries dejan de matchear."""
        body = search._build_baseline_qdrant_bm25_body({"823349694": 1.0}, size=1, scoring="linear")
        clause = body["query"]["bool"]["should"][0]
        assert clause["rank_feature"]["field"] == "baseline_qdrant_bm25.823349694"

    def test_empty_weights_returns_match_none(self):
        """Una query que tras tokenizar quedó sin stems debe producir
        `match_none`, no un bool/should vacío (que OpenSearch interpreta
        como match-all en algunas versiones)."""
        body = search._build_baseline_qdrant_bm25_body({}, size=5, scoring="linear")
        assert body["query"] == {"match_none": {}}
        assert body["size"] == 0

    def test_zero_or_negative_weights_filtered(self):
        """Las claves con peso ≤ 0 se omiten para evitar el 400 que tira
        OpenSearch contra rank_features con valores no positivos."""
        weights = {"1": 0.5, "2": 0.0, "3": -0.1, "4": 2.0}
        body = search._build_baseline_qdrant_bm25_body(weights, size=5, scoring="linear")
        fields = [c["rank_feature"]["field"] for c in body["query"]["bool"]["should"]]
        assert "baseline_qdrant_bm25.1" in fields
        assert "baseline_qdrant_bm25.4" in fields
        assert "baseline_qdrant_bm25.2" not in fields
        assert "baseline_qdrant_bm25.3" not in fields
