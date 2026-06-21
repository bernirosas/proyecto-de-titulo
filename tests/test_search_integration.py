"""Tests del flow completo de `search.search()` con OpenSearch stubeado.

`search.search()` orquesta preprocesamiento de query + construcción del body
+ I/O a OpenSearch + formateo de hits + highlights. Sus helpers individuales
(`_build_bm25_body`, etc.) ya están testeados en `test_search.py`. Acá
verificamos la **integración**: que las ramas (bm25 / tfidf / splade /
baseline_qdrant_bm25) se conecten correctamente entre sí.

Stubeamos:
  - `clients.get_opensearch` → un cliente fake que devuelve hits
    deterministas. Sin stub haría falta una instancia real de OpenSearch.
  - Encoders pesados (`splade_encoder`, `baseline_qdrant_encoder`) →
    funciones que devuelven dicts fijos. Sin stub haría falta descargar
    los modelos ONNX/transformers, lo cual es desproporcionado para tests
    unitarios del orquestador.

Lo que sí ejercitamos sin stub:
  - El dispatch de método → rama correcta del if/elif
  - La construcción de la respuesta (`query_terms`, `query_input_tokens`,
    `latency_ms`, `query_tokens`, etc.)
  - El timing (latency_ms > 0 y < algún umbral razonable)
"""

from __future__ import annotations

import pytest


def _fake_opensearch_response(uuids: list[str], scores: list[float]) -> dict:
    """Construye una respuesta tipo OpenSearch con hits deterministas."""
    return {
        "hits": {
            "total": {"value": len(uuids)},
            "hits": [
                {
                    "_score": score,
                    "_source": {
                        "chunk_uuid": uuid,
                        "chunk_id": i,
                        "name": f"Doc {i}",
                        "source_type": "ley",
                        "content": f"contenido del chunk {uuid}",
                    },
                }
                for i, (uuid, score) in enumerate(zip(uuids, scores, strict=False))
            ],
        }
    }


class _FakeOpenSearchClient:
    """Cliente OpenSearch stubeado. Captura el body de la última búsqueda
    para que los tests puedan inspeccionarlo si lo necesitan."""

    def __init__(self, response: dict) -> None:
        self._response = response
        self.last_body: dict | None = None
        self.last_index: str | None = None

    def search(self, *, index: str, body: dict) -> dict:
        self.last_index = index
        self.last_body = body
        return self._response


@pytest.fixture
def fake_os_response():
    """Respuesta canónica de OpenSearch usada por los tests del orquestador."""
    return _fake_opensearch_response(
        uuids=["aaa", "bbb", "ccc"],
        scores=[3.5, 2.7, 1.2],
    )


@pytest.fixture
def patched_clients(monkeypatch, fake_os_response):
    """Reemplaza `clients.get_opensearch` por un fake que devuelve
    `fake_os_response`. Devuelve el cliente fake para que el test pueda
    inspeccionar lo que se envió."""
    from src import clients

    fake = _FakeOpenSearchClient(fake_os_response)
    monkeypatch.setattr(clients, "get_opensearch", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# BM25 (p1, p2, p3) y TFIDF (p1, p2, p3): no requieren encoder externo.
# ---------------------------------------------------------------------------


class TestSearchBM25Branch:
    def test_p1_bm25_returns_formatted_response(self, patched_clients):
        """Rama bm25 + p1: el response debe traer hits formateados,
        preproc y vectorizer correctos, y latencia > 0."""
        from src import search

        result = search.search("plazo prescripción impuestos", method="p1_bm25", size=3)

        assert result["method"] == "p1_bm25"
        assert result["preproc"] == "p1"
        assert result["vectorizer"] == "bm25"
        assert result["total"] == 3
        assert len(result["hits"]) == 3
        assert result["hits"][0]["chunk_uuid"] == "aaa"
        assert result["hits"][0]["score"] == 3.5
        assert result["latency_ms"] >= 0  # warm puede ser <1ms

    def test_p3_bm25_uses_content_p3_field(self, patched_clients):
        """Sanity: el body enviado a OpenSearch usa `content_p3` (no p1)."""
        from src import search

        search.search("test", method="p3_bm25", size=5)
        body = patched_clients.last_body
        assert "content_p3" in body["query"]["match"]

    def test_bm25_with_tuned_a_uses_sibling_field(self, patched_clients):
        """Si el usuario pide scoring=tuned_a, el body apunta al campo
        hermano `content_p1_a` (no al base `content_p1`)."""
        from src import search

        search.search("test", method="p1_bm25", size=3, scoring="tuned_a")
        body = patched_clients.last_body
        assert "content_p1_a" in body["query"]["match"]


class TestSearchTfidfBranch:
    def test_tfidf_response_includes_query_terms(self, patched_clients):
        """Rama tfidf: query_terms debe traer cada token con su TF como peso."""
        from src import search

        result = search.search("iva iva fiscal", method="p2_tfidf", size=3)
        assert result["vectorizer"] == "tfidf"
        # query_vector mapea token a TF crudo
        assert result["query_vector"]["iva"] == 2.0
        assert result["query_vector"]["fiscal"] == 1.0

    def test_tfidf_with_saturation_scoring(self, patched_clients):
        """Variante saturation_p1: el body lleva la cláusula
        `saturation: {pivot: 1.0}`, no `linear`."""
        from src import search

        search.search("test", method="p3_tfidf", size=3, scoring="saturation_p1")
        body = patched_clients.last_body
        clause = body["query"]["bool"]["should"][0]["rank_feature"]
        assert "saturation" in clause
        assert clause["saturation"]["pivot"] == 1.0


# ---------------------------------------------------------------------------
# SPLADE: requiere stub del encoder neuronal.
# ---------------------------------------------------------------------------


class TestSearchSpladeBranch:
    def test_splade_branch_calls_encoder_and_formats(self, patched_clients, monkeypatch):
        """Rama splade: el encoder neuronal devuelve `{wordpiece: peso}`,
        y el body construido apunta a `splade_pX.<wordpiece>`."""
        from src import search, splade_encoder

        monkeypatch.setattr(
            splade_encoder, "encode", lambda text, top_k=128: {"plazo": 1.5, "##cion": 0.8}
        )
        # compute_highlights para SPLADE intenta cargar el tokenizer real
        # del encoder (torch + transformers). Stubeamos directamente la
        # función de highlights y `_ensure_loaded` para que sean no-ops.
        monkeypatch.setattr(search, "compute_highlights", lambda content, qv, preproc, vec: {})
        monkeypatch.setattr(splade_encoder, "_ensure_loaded", lambda: None)
        # `tokenize_query` también tira tokenizer real; stub que devuelve
        # los wordpieces ya conocidos.
        monkeypatch.setattr(splade_encoder, "tokenize_query", lambda q: ["plazo", "##cion"])

        result = search.search("plazo de prescripción", method="p1_splade", size=3)

        assert result["vectorizer"] == "splade"
        # query_vector son los pesos del encoder, no TF
        assert result["query_vector"] == {"plazo": 1.5, "##cion": 0.8}
        # El body apunta al campo splade
        body = patched_clients.last_body
        fields = [c["rank_feature"]["field"] for c in body["query"]["bool"]["should"]]
        assert "splade_p1.plazo" in fields
        assert "splade_p1.##cion" in fields


# ---------------------------------------------------------------------------
# baseline_qdrant_bm25: requiere stub del encoder fastembed.
# ---------------------------------------------------------------------------


class TestSearchBaselineQdrantBranch:
    def test_baseline_dispatches_to_fastembed_encoder(self, patched_clients, monkeypatch):
        """La rama baseline_qdrant_bm25 NO pasa por _split_method (formato
        no-canónico). Debe invocar al encoder fastembed y construir el body
        contra el campo `baseline_qdrant_bm25.<hash>`."""
        from src import baseline_qdrant_encoder, search

        # Stub: encoder devuelve dos hashes (str) con TF como peso.
        monkeypatch.setattr(
            baseline_qdrant_encoder,
            "encode_with_stems",
            lambda text: (
                {"123": 1.0, "456": 2.0},
                {"123": "plazo", "456": "impuest"},
                ["plazo", "impuest"],
            ),
        )
        result = search.search("plazo impuestos", method="baseline_qdrant_bm25", size=3)

        assert result["method"] == "baseline_qdrant_bm25"
        assert result["preproc"] == "qdrant"
        assert result["vectorizer"] == "baseline_bm25"
        # query_vector trae los hashes (string) como claves
        assert result["query_vector"]["123"] == 1.0
        # Body apunta al campo baseline_qdrant_bm25.<hash>
        body = patched_clients.last_body
        fields = [c["rank_feature"]["field"] for c in body["query"]["bool"]["should"]]
        assert "baseline_qdrant_bm25.123" in fields
        assert "baseline_qdrant_bm25.456" in fields

    def test_baseline_exposes_stems_as_input_tokens_when_available(
        self, patched_clients, monkeypatch
    ):
        """Cuando fastembed expone el pipeline interno, la UI muestra los
        stems legibles (no los hashes) como query_input_tokens. Validamos
        que la respuesta los preserve."""
        from src import baseline_qdrant_encoder, search

        monkeypatch.setattr(
            baseline_qdrant_encoder,
            "encode_with_stems",
            lambda text: ({"123": 1.0}, {"123": "plazo"}, ["plazo"]),
        )
        result = search.search("plazo", method="baseline_qdrant_bm25", size=3)
        assert "plazo" in result["query_input_tokens"]

    def test_baseline_falls_back_to_hashes_when_pipeline_unavailable(
        self, patched_clients, monkeypatch
    ):
        """Si fastembed no expone el pipeline interno (versión nueva o
        regresión), el encoder devuelve `(weights, {}, [])`. La función
        debe degradar mostrando los hashes en `query_input_tokens` en vez
        de explotar."""
        from src import baseline_qdrant_encoder, search

        monkeypatch.setattr(
            baseline_qdrant_encoder,
            "encode_with_stems",
            lambda text: ({"123": 1.0, "456": 2.0}, {}, []),
        )
        result = search.search("plazo", method="baseline_qdrant_bm25", size=3)
        # Cae a los hashes como tokens visibles para la UI
        assert set(result["query_input_tokens"]) == {"123", "456"}


# ---------------------------------------------------------------------------
# Respuesta a hits vacíos (corner case que la UI debe manejar)
# ---------------------------------------------------------------------------


class TestSearchEmptyHits:
    def test_returns_empty_hits_array_when_opensearch_returns_none(self, monkeypatch):
        """Si OpenSearch responde sin hits, la respuesta debe tener
        `hits=[]` y `total=0` sin truenar."""
        from src import clients, search

        monkeypatch.setattr(clients, "get_opensearch", lambda: _FakeOpenSearchClient({"hits": {}}))
        result = search.search("test", method="p1_bm25", size=3)
        assert result["total"] == 0
        assert result["hits"] == []
