"""Tests del modo híbrido RRF.

Cubre tres capas:

  1. La función pura `_reciprocal_rank_fusion`: corrección numérica del
     score (1/(k+r)), comportamiento ante asimetrías (chunk en una sola
     lista) y determinismo en empates exactos.

  2. `dense_qdrant` (lookup + búsqueda Qdrant) con cliente stubeado.

  3. El orquestador `search.search(method='hybrid_rrf', ...)` con
     OpenSearch + Qdrant + queries_dense.json todos stubeados.

No requerimos servicios reales corriendo — los stubs son determinísticos.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# 1. _reciprocal_rank_fusion — función pura
# ---------------------------------------------------------------------------


class TestReciprocalRankFusion:
    def test_canonical_two_list_fusion(self):
        """Caso típico: dos listas con dos elementos cada una. Verifica
        los scores numéricos contra la fórmula del paper."""
        from src import search

        dense = [{"chunk_uuid": "a", "rank": 1}, {"chunk_uuid": "b", "rank": 2}]
        sparse = [{"chunk_uuid": "b", "rank": 1}, {"chunk_uuid": "a", "rank": 2}]
        fused = search._reciprocal_rank_fusion([dense, sparse], k=60)

        # `a`: 1/(60+1) + 1/(60+2); `b`: 1/(60+2) + 1/(60+1) — idénticos
        assert fused[0]["chunk_uuid"] in {"a", "b"}
        score_a = next(f for f in fused if f["chunk_uuid"] == "a")["rrf_score"]
        score_b = next(f for f in fused if f["chunk_uuid"] == "b")["rrf_score"]
        assert score_a == pytest.approx(score_b)
        assert score_a == pytest.approx(1.0 / 61 + 1.0 / 62)

    def test_asymmetric_membership(self):
        """Un chunk que aparece sólo en una lista no recibe penalty
        explícito — su contribución desde la otra lista es 0."""
        from src import search

        dense = [{"chunk_uuid": "a", "rank": 1}]
        sparse = [{"chunk_uuid": "b", "rank": 1}]
        fused = search._reciprocal_rank_fusion([dense, sparse], k=60)

        scores = {f["chunk_uuid"]: f["rrf_score"] for f in fused}
        assert scores["a"] == pytest.approx(1.0 / 61)
        assert scores["b"] == pytest.approx(1.0 / 61)
        # `a` aparece sólo en la lista 0 (denso) — su rank en sparse debe ser None
        for f in fused:
            if f["chunk_uuid"] == "a":
                assert f["ranks"] == [1, None]
            else:
                assert f["ranks"] == [None, 1]

    def test_top_chunk_in_both_lists_outranks_one_sided(self):
        """Un chunk que aparece en ambas listas (ambas en posición media)
        debe quedar arriba de un chunk top-1 en una sola lista. Es la razón
        por la que RRF funciona mejor que pick-the-best."""
        from src import search

        dense = [
            {"chunk_uuid": "solo_d", "rank": 1},  # top-1 sólo en denso
            {"chunk_uuid": "both", "rank": 5},  # rank-5 en denso
        ]
        sparse = [
            {"chunk_uuid": "solo_s", "rank": 1},  # top-1 sólo en sparse
            {"chunk_uuid": "both", "rank": 5},  # rank-5 en sparse
        ]
        fused = search._reciprocal_rank_fusion([dense, sparse], k=60)

        # `both`: 1/65 + 1/65 ≈ 0.0308
        # `solo_d`: 1/61 ≈ 0.0164
        # → `both` debería estar primero
        assert fused[0]["chunk_uuid"] == "both"

    def test_tie_break_by_chunk_uuid(self):
        """Cuando dos chunks empatan exactamente en RRF score, el orden
        se resuelve por chunk_uuid ascendente. Determinismo es importante
        para que el benchmark sea reproducible run-to-run."""
        from src import search

        # Dos chunks con ranks simétricos → mismo score exacto
        dense = [{"chunk_uuid": "z", "rank": 1}, {"chunk_uuid": "a", "rank": 2}]
        sparse = [{"chunk_uuid": "a", "rank": 1}, {"chunk_uuid": "z", "rank": 2}]
        fused = search._reciprocal_rank_fusion([dense, sparse], k=60)
        # Mismo score, tie-break alfabético → "a" antes que "z"
        assert fused[0]["chunk_uuid"] == "a"
        assert fused[1]["chunk_uuid"] == "z"

    def test_empty_rankings_returns_empty(self):
        """Ambas listas vacías → no hay nada que fusionar."""
        from src import search

        assert search._reciprocal_rank_fusion([[], []]) == []

    def test_one_empty_ranking_passes_through(self):
        """Una lista vacía + una con elementos → output igual al input no-vacío
        (con metadatos de ranks que muestran el None en la lista vacía)."""
        from src import search

        sparse = [{"chunk_uuid": "x", "rank": 1}, {"chunk_uuid": "y", "rank": 2}]
        fused = search._reciprocal_rank_fusion([[], sparse], k=60)
        assert [f["chunk_uuid"] for f in fused] == ["x", "y"]
        # Ranks: posición 0 = denso (vacío) → None; posición 1 = sparse → rank
        for f in fused:
            assert f["ranks"][0] is None
            assert f["ranks"][1] in {1, 2}

    def test_k_parameter_controls_decay(self):
        """k chico hace que el top-1 domine; k grande aplana la distribución.
        Verifica que el parámetro efectivamente cambia los scores."""
        from src import search

        ranking = [{"chunk_uuid": "a", "rank": 1}, {"chunk_uuid": "b", "rank": 10}]
        fused_small = search._reciprocal_rank_fusion([ranking], k=0)
        fused_big = search._reciprocal_rank_fusion([ranking], k=1000)
        gap_small = fused_small[0]["rrf_score"] - fused_small[1]["rrf_score"]
        gap_big = fused_big[0]["rrf_score"] - fused_big[1]["rrf_score"]
        # k chico debería producir una brecha mayor entre top-1 y rank-10
        assert gap_small > gap_big

    def test_negative_k_raises(self):
        """`k` debe ser >= 0 (Cormack default = 60). k negativo no tiene
        sentido y produciría división por cero si rank == |k|."""
        from src import search

        with pytest.raises(ValueError, match="k debe ser"):
            search._reciprocal_rank_fusion([], k=-1)

    def test_ranks_metadata_preserves_list_order(self):
        """El contrato dice: rankings[0] aporta a ranks[0], rankings[1] a
        ranks[1]. Si esto se rompe la UI no sabría qué rank vino de dónde."""
        from src import search

        ranking_0 = [{"chunk_uuid": "x", "rank": 7}]
        ranking_1 = [{"chunk_uuid": "x", "rank": 3}]
        fused = search._reciprocal_rank_fusion([ranking_0, ranking_1], k=60)
        cell = fused[0]
        assert cell["ranks"] == [7, 3]


# ---------------------------------------------------------------------------
# 2. dense_qdrant — lookup + Qdrant client stubeado
# ---------------------------------------------------------------------------


class _FakeQdrantClient:
    """Cliente Qdrant stubeado. Soporta `query_points` con vector + limit;
    devuelve puntos predefinidos cuya `payload['id']` da el chunk_uuid."""

    def __init__(self, points: list) -> None:
        self._points = points

    def query_points(self, *, collection_name, query, using, limit, with_payload, with_vectors):
        del collection_name, query, using, with_payload, with_vectors
        return SimpleNamespace(points=self._points[:limit])


def _fake_qdrant_point(uuid: str, score: float, point_id: str = "internal-id"):
    """Construye un punto Qdrant tipo `query_points()` response."""
    return SimpleNamespace(id=point_id, score=score, payload={"id": uuid})


class TestDenseQdrantLookup:
    def test_get_query_vector_returns_precomputed(self, monkeypatch, tmp_path):
        """`get_query_vector(qid)` lee del JSON cacheado y devuelve la lista."""
        from src import config, dense_qdrant

        # Reset cache antes de cada test
        monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", None)

        # Crear archivo temporal con 1 query
        path = tmp_path / "queries_dense.json"
        path.write_text(
            '{"q000": ' + str([0.1] * 3072) + "}",
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "QUERIES_DENSE_PATH", str(path))

        v = dense_qdrant.get_query_vector("q000")
        assert len(v) == 3072
        assert v[0] == pytest.approx(0.1)

    def test_get_query_vector_missing_id_raises(self, monkeypatch, tmp_path):
        """ID no presente → ValueError con mensaje accionable."""
        from src import config, dense_qdrant

        monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", None)
        path = tmp_path / "queries_dense.json"
        path.write_text('{"q000": ' + str([0.1] * 3072) + "}", encoding="utf-8")
        monkeypatch.setattr(config, "QUERIES_DENSE_PATH", str(path))

        with pytest.raises(ValueError, match="q999"):
            dense_qdrant.get_query_vector("q999")

    def test_missing_file_raises_file_not_found(self, monkeypatch, tmp_path):
        """Si el JSON no existe, debemos romper explícito — el modo híbrido
        no puede operar sin él. Mejor 5xx claro que silenciar."""
        from src import config, dense_qdrant

        monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", None)
        monkeypatch.setattr(config, "QUERIES_DENSE_PATH", str(tmp_path / "no-existe.json"))

        with pytest.raises(FileNotFoundError, match="embed_queries_gemini"):
            dense_qdrant.get_query_vector("q000")

    def test_wrong_dimension_raises(self, monkeypatch, tmp_path):
        """Validación de dimensión: 3072 esperado. Detecta archivos de otro
        modelo o regenerados con `output_dimensionality` distinto."""
        from src import config, dense_qdrant

        monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", None)
        path = tmp_path / "queries_dense.json"
        path.write_text('{"q000": [0.1, 0.2, 0.3]}', encoding="utf-8")
        monkeypatch.setattr(config, "QUERIES_DENSE_PATH", str(path))

        with pytest.raises(ValueError, match="dimensión"):
            dense_qdrant.get_query_vector("q000")

    def test_search_dense_returns_ranked_chunks(self, monkeypatch):
        """`search_dense()` devuelve hits con `chunk_uuid` extraído del
        payload, `score` del similarity y `rank` 1-indexado."""
        from src import clients, dense_qdrant

        points = [
            _fake_qdrant_point("uuid-a", 0.95),
            _fake_qdrant_point("uuid-b", 0.80),
            _fake_qdrant_point("uuid-c", 0.65),
        ]
        monkeypatch.setattr(clients, "get_qdrant", lambda: _FakeQdrantClient(points))

        hits = dense_qdrant.search_dense([0.1] * 3072, top_k=3)
        assert [h["chunk_uuid"] for h in hits] == ["uuid-a", "uuid-b", "uuid-c"]
        assert [h["rank"] for h in hits] == [1, 2, 3]
        assert hits[0]["score"] == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# 3. search(method='hybrid_rrf', ...) — flow completo con stubs
# ---------------------------------------------------------------------------


def _hybrid_setup(monkeypatch, dense_uuids, sparse_uuids, *, query_id="q000"):
    """Helper que stubea Qdrant, OpenSearch y el JSON de queries para que
    `search('hybrid_rrf', ...)` corra contra rankings deterministas."""
    from src import clients, dense_qdrant

    # Stub queries_dense: una query con vector dummy.
    monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", {query_id: [0.1] * 3072})

    # Stub Qdrant: devuelve `dense_uuids` en orden.
    qdrant_points = [_fake_qdrant_point(uuid, 1.0 - 0.01 * i) for i, uuid in enumerate(dense_uuids)]
    monkeypatch.setattr(clients, "get_qdrant", lambda: _FakeQdrantClient(qdrant_points))

    # Stub OpenSearch: la primera llamada devuelve el ranking sparse;
    # la segunda (si hay) re-hidrata el `_source` de los UUIDs missing.
    sparse_response = {
        "hits": {
            "total": {"value": len(sparse_uuids)},
            "hits": [
                {
                    "_score": 10.0 - i,
                    "_source": {
                        "chunk_uuid": uuid,
                        "chunk_id": i,
                        "name": f"sparse-{uuid}",
                        "content": f"contenido {uuid}",
                    },
                }
                for i, uuid in enumerate(sparse_uuids)
            ],
        }
    }
    rehydrate_response = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_score": 0.0,
                    "_source": {
                        "chunk_uuid": uuid,
                        "chunk_id": -1,
                        "name": f"dense-only-{uuid}",
                        "content": f"contenido denso {uuid}",
                    },
                }
                for uuid in set(dense_uuids) - set(sparse_uuids)
            ],
        }
    }

    class _SeqOSClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def search(self, *, index, body):
            self.calls.append({"index": index, "body": body})
            if len(self.calls) == 1:
                return sparse_response
            return rehydrate_response

    fake_os = _SeqOSClient()
    monkeypatch.setattr(clients, "get_opensearch", lambda: fake_os)
    return fake_os


class TestSearchHybridRRF:
    def test_dispatches_correctly(self, monkeypatch):
        """`method=hybrid_rrf` debe llegar al branch híbrido, no a
        `_split_method` (que rechaza nombres no-canónicos)."""
        _hybrid_setup(monkeypatch, dense_uuids=["a", "b"], sparse_uuids=["a", "c"])
        from src import search

        result = search.search(
            query="texto cualquiera", method="hybrid_rrf", size=2, query_id="q000"
        )
        assert result["method"] == "hybrid_rrf"
        assert result["vectorizer"] == "hybrid_rrf"

    def test_response_has_fusion_components(self, monkeypatch):
        """El response debe incluir metadatos de la fusión: k, sparse_method,
        modelo denso, conteos de cada lado."""
        _hybrid_setup(monkeypatch, dense_uuids=["a"], sparse_uuids=["a"])
        from src import config, search

        result = search.search(
            query="x", method="hybrid_rrf", size=1, scoring="p3_bm25", query_id="q000"
        )
        fc = result["fusion_components"]
        assert fc["rrf_k"] == config.RRF_K
        assert fc["sparse_method"] == "p3_bm25"
        assert fc["dense_model"] == "gemini-embedding-001"
        assert fc["query_id"] == "q000"

    def test_hits_carry_rank_dense_and_rank_sparse(self, monkeypatch):
        """Cada hit del response híbrido debe traer `rank_dense` y
        `rank_sparse` para que la UI muestre el aporte de cada lado."""
        _hybrid_setup(monkeypatch, dense_uuids=["a", "b"], sparse_uuids=["a", "c"])
        from src import search

        result = search.search(query="x", method="hybrid_rrf", size=3, query_id="q000")
        # `a` aparece en ambos → ambos ranks no-None
        a_hit = next(h for h in result["hits"] if h["chunk_uuid"] == "a")
        assert a_hit["rank_dense"] == 1
        assert a_hit["rank_sparse"] == 1
        # `c` sólo en sparse → rank_dense es None
        c_hit = next((h for h in result["hits"] if h["chunk_uuid"] == "c"), None)
        if c_hit is not None:
            assert c_hit["rank_dense"] is None
            assert c_hit["rank_sparse"] == 2

    def test_missing_query_id_raises(self, monkeypatch):
        """Pedir hybrid_rrf sin query_id → ValueError (HTTP 400 en la API)."""
        _hybrid_setup(monkeypatch, dense_uuids=[], sparse_uuids=[])
        from src import search

        with pytest.raises(ValueError, match="query_id"):
            search.search(query="x", method="hybrid_rrf", size=5, query_id=None)

    def test_invalid_sparse_partner_raises(self, monkeypatch):
        """`scoring` debe ser un sparse partner válido. Un valor random
        rompe explícito antes de tocar OpenSearch."""
        _hybrid_setup(monkeypatch, dense_uuids=["a"], sparse_uuids=["a"])
        from src import search

        with pytest.raises(ValueError, match="sparse_method"):
            search.search(
                query="x",
                method="hybrid_rrf",
                size=1,
                scoring="not_a_real_partner",
                query_id="q000",
            )

    def test_default_sparse_partner_used_when_scoring_none(self, monkeypatch):
        """Si scoring es None, debe usarse `DEFAULT_HYBRID_SPARSE`."""
        _hybrid_setup(monkeypatch, dense_uuids=["a"], sparse_uuids=["a"])
        from src import config, search

        result = search.search(query="x", method="hybrid_rrf", size=1, query_id="q000")
        assert result["scoring"] == config.DEFAULT_HYBRID_SPARSE

    def test_size_limits_top_k_after_fusion(self, monkeypatch):
        """Aunque la pool de fusión sea grande, el output respeta `size`."""
        _hybrid_setup(
            monkeypatch,
            dense_uuids=[f"u{i:02d}" for i in range(20)],
            sparse_uuids=[f"u{i:02d}" for i in range(5, 25)],
        )
        from src import search

        result = search.search(query="x", method="hybrid_rrf", size=3, query_id="q000")
        assert len(result["hits"]) == 3
