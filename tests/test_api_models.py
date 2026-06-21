"""Tests del contrato del modelo Pydantic expuesto por la API.

Se eliminaron los tests que verificaban funciones propias de Pydantic
(rechazo de tamaños fuera de rango, consultas vacías, métodos
desconocidos): esa lógica la garantiza la propia librería y testearla
duplica esfuerzo sin detectar fallas adicionales.

Lo único que se mantiene es la verificación de sincronía entre el
catálogo `config.TECHNIQUES` y el `Literal` declarado en
`scripts/api.py`: si se incorpora una técnica al catálogo y se olvida
agregarla al Literal de Pydantic, FastAPI rechaza solicitudes válidas
con 422 sin que ningún otro test lo detecte. Esa divergencia constituye
una falla real y silenciosa.
"""

from __future__ import annotations

from typing import get_args

from src import config

from api import MethodLiteral, techniques


def test_pydantic_literal_matches_techniques_catalog():
    """Toda técnica declarada en config.TECHNIQUES debe estar también en
    el Literal de Pydantic, y viceversa."""
    literal_methods = set(get_args(MethodLiteral))
    catalog_methods = set(config.TECHNIQUES)
    assert literal_methods == catalog_methods, (
        "Divergencia entre el Literal de Pydantic y config.TECHNIQUES.\n"
        f"  Solo en Pydantic: {literal_methods - catalog_methods}\n"
        f"  Solo en catálogo: {catalog_methods - literal_methods}"
    )


def test_techniques_endpoint_declares_scoring_family():
    """Cada técnica del catálogo expuesto por GET /techniques debe declarar
    `scoring_family` con valor `bm25` o `rank_feature`. Sin esta validación,
    el frontend caería al fallback heurístico que falla para
    `baseline_qdrant_bm25` (vectorización nominalmente BM25 pero servida
    por rank_features), ofreciendo al usuario variantes de scoring
    incompatibles con el motor real."""
    catalog = techniques()["techniques"]
    valid_families = {"bm25", "rank_feature", "hybrid"}
    for tech in catalog:
        assert "scoring_family" in tech, f"técnica {tech['id']!r} no declara scoring_family"
        assert tech["scoring_family"] in valid_families, (
            f"técnica {tech['id']!r} tiene scoring_family inválido: "
            f"{tech['scoring_family']!r} (esperado: {valid_families})"
        )


def test_techniques_endpoint_ids_match_catalog():
    """Cada técnica devuelta por /techniques debe estar en config.TECHNIQUES
    y viceversa — protege contra olvidar agregar/quitar técnicas del
    endpoint cuando se cambia el catálogo."""
    catalog_ids = {t["id"] for t in techniques()["techniques"]}
    config_ids = set(config.TECHNIQUES)
    assert catalog_ids == config_ids, (
        "Desincronía entre /techniques y config.TECHNIQUES.\n"
        f"  Solo en endpoint: {catalog_ids - config_ids}\n"
        f"  Solo en config:   {config_ids - catalog_ids}"
    )


def test_baseline_qdrant_bm25_uses_rank_feature_family():
    """Test explícito de regresión: la baseline_qdrant_bm25 NO debe
    declarar `scoring_family=bm25` aunque su `vectorization` mencione
    'BM25'. Se sirve por `rank_features` en OpenSearch, así que el
    selector de scoring de la UI debe ofrecer linear/saturation, no
    tuned_a/b/c. Este test atrapa el bug donde el frontend infería
    `bm25` por `vectorization.startsWith('bm25')`."""
    catalog = {t["id"]: t for t in techniques()["techniques"]}
    assert catalog["baseline_qdrant_bm25"]["scoring_family"] == "rank_feature"


# ---------------------------------------------------------------------------
# Tests TestClient: golpean el endpoint HTTP real, no solo la función Python.
# Atrapan el caso donde la función está bien en disco pero el servidor
# responde algo distinto (módulo cargado en memoria desactualizado, ruta
# mal registrada en FastAPI, validación Pydantic que rechaza la respuesta).
# ---------------------------------------------------------------------------


def test_techniques_endpoint_http_returns_baseline():
    """GET /techniques debe responder 200 con baseline_qdrant_bm25 en el
    catálogo. Si este test pasa pero el contenedor en producción no
    devuelve la baseline, es porque uvicorn está sirviendo desde memoria
    una versión vieja del módulo — restart del contenedor o `--reload`."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.get("/techniques")

    assert response.status_code == 200, f"esperado 200, recibido {response.status_code}"
    payload = response.json()
    assert "techniques" in payload, "respuesta sin clave 'techniques'"

    ids = {t["id"] for t in payload["techniques"]}
    assert "baseline_qdrant_bm25" in ids, (
        f"baseline_qdrant_bm25 ausente del endpoint /techniques. " f"IDs presentes: {sorted(ids)}"
    )


def test_techniques_endpoint_http_returns_all_techniques():
    """Contrato del catálogo: el endpoint expone exactamente las técnicas
    que `config.TECHNIQUES` declara. Si en el futuro se agrega una nueva
    (p. ej. BGE-M3), este test forzará a actualizar el endpoint en el
    mismo PR."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.get("/techniques")
    payload = response.json()

    assert len(payload["techniques"]) == len(config.TECHNIQUES), (
        f"endpoint expone {len(payload['techniques'])} técnicas pero "
        f"config.TECHNIQUES declara {len(config.TECHNIQUES)}"
    )


def test_scoring_variants_endpoint_http_returns_all_families():
    """GET /scoring-variants debe responder con las tres familias
    (`bm25`, `rank_feature` y `hybrid`) que el frontend consulta para
    poblar el segundo dropdown según la técnica seleccionada."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.get("/scoring-variants")

    assert response.status_code == 200
    payload = response.json()
    for fam in ("bm25", "rank_feature", "hybrid"):
        assert fam in payload, f"familia {fam!r} ausente"
        assert isinstance(payload[fam], list) and len(payload[fam]) > 0
    # Defaults explícitos por familia.
    assert "defaults" in payload
    for fam in ("bm25", "rank_feature", "hybrid"):
        assert fam in payload["defaults"]


def test_hybrid_rrf_in_techniques_catalog():
    """`hybrid_rrf` debe aparecer en /techniques con `scoring_family=hybrid`,
    no como bm25 ni rank_feature. La UI usa eso para decidir si muestra
    el dropdown de queries en vez del input de texto libre."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    payload = client.get("/techniques").json()
    catalog = {t["id"]: t for t in payload["techniques"]}
    assert "hybrid_rrf" in catalog
    assert catalog["hybrid_rrf"]["scoring_family"] == "hybrid"


def test_benchmark_queries_endpoint_returns_list(tmp_path, monkeypatch):
    """`/benchmark-queries` debe leer el directorio de queries y devolver
    una lista con `query_id`, `query_text` y `has_dense`. Sin este endpoint
    el frontend no puede poblar el dropdown de hybrid_rrf."""
    import json as _json

    from fastapi.testclient import TestClient
    from src import config, dense_qdrant

    from api import app

    # Crear un par de query files dummy en tmp_path
    (tmp_path / "q000_x.json").write_text(
        _json.dumps({"query_id": "q000", "query_text": "Plazo de prescripción"}),
        encoding="utf-8",
    )
    (tmp_path / "q001_y.json").write_text(
        _json.dumps({"query_id": "q001", "query_text": "IVA arriendo"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "QUERIES_DIR", str(tmp_path))
    # Marcar q000 como con embedding denso disponible; q001 sin él.
    monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", {"q000": [0.0] * 3072})

    client = TestClient(app)
    response = client.get("/benchmark-queries")
    assert response.status_code == 200
    payload = response.json()
    ids = {q["query_id"] for q in payload["queries"]}
    assert ids == {"q000", "q001"}
    has_dense = {q["query_id"]: q["has_dense"] for q in payload["queries"]}
    assert has_dense == {"q000": True, "q001": False}
    assert payload["total"] == 2
    assert payload["with_dense"] == 1


def test_search_rejects_hybrid_rrf_without_query_id(monkeypatch):
    """`hybrid_rrf` sin `query_id` debe romper con 400 (ValueError →
    HTTPException). Sin este check, el usuario obtendría un 500 críptico."""
    from fastapi.testclient import TestClient
    from src import dense_qdrant

    from api import app

    monkeypatch.setattr(dense_qdrant, "_QUERIES_CACHE", {"q000": [0.0] * 3072})
    client = TestClient(app)
    response = client.post(
        "/search",
        json={"query": "x", "method": "hybrid_rrf", "size": 5},
    )
    assert response.status_code == 400
    assert "query_id" in response.json()["detail"]


def test_search_request_rejects_unknown_method():
    """Contrato 422: si la UI manda un `method` que no está en MethodLiteral,
    FastAPI debe rechazar con 422 (Unprocessable Entity), no 500. Esto
    pasa automáticamente por Pydantic — el test fija el comportamiento
    como contrato."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.post(
        "/search",
        json={"query": "test", "method": "p9_inexistente", "size": 5},
    )
    assert (
        response.status_code == 422
    ), f"esperado 422 para método inválido, recibido {response.status_code}"


def test_search_request_rejects_empty_query():
    """`query` tiene `min_length=1` en el Pydantic model. Strings vacíos
    deben rechazarse con 422 sin llegar a search()."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.post(
        "/search",
        json={"query": "", "method": "p1_bm25", "size": 5},
    )
    assert response.status_code == 422


def test_search_request_rejects_size_out_of_range():
    """`size` tiene `ge=1, le=100`. Valores fuera de rango → 422."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    for bad_size in (0, -1, 101, 1000):
        response = client.post(
            "/search",
            json={"query": "test", "method": "p1_bm25", "size": bad_size},
        )
        assert response.status_code == 422, (
            f"size={bad_size} debería rechazarse con 422, " f"recibido {response.status_code}"
        )


def test_healthz_endpoint():
    """`/healthz` es el liveness probe. Debe responder 200 con
    `{"status": "ok"}` sin tocar OpenSearch ni Qdrant — sirve para
    chequear que el proceso FastAPI está vivo aún si los servicios
    externos están caídos."""
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
