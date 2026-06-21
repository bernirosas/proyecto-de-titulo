"""Endpoint FastAPI para búsqueda esparsa sobre `chunks_maqui`.

Endpoints:
    GET  /healthz                  -> liveness
    GET  /techniques               -> lista las 9 técnicas soportadas (8 sparse + hybrid_rrf)
    GET  /scoring-variants         -> variantes por familia (bm25/rank_feature/hybrid)
    GET  /benchmark-queries        -> queries del benchmark (para el dropdown de hybrid_rrf)
    POST /search                   -> ejecuta búsqueda
    GET  /                         -> sirve el frontend estático

Uso (desde el host):
    docker compose up -d opensearch qdrant
    docker compose run --rm --service-ports app uvicorn scripts.api:app --host 0.0.0.0 --port 8000

    # luego abrir http://localhost:8000/
"""

import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from opensearchpy.exceptions import OpenSearchException
from pydantic import BaseModel, Field
from src import config, search
from src.gemini_embed import GeminiEmbedError

# -----------------------------------------------------------------------------
# Modelos Pydantic
# -----------------------------------------------------------------------------

# Ojo: Literal acepta strings, no tuplas. Hardcodeamos para que Pydantic
# valide en el JSON Schema. Mantener sincronizado con config.TECHNIQUES.
MethodLiteral = Literal[
    "p1_bm25",
    "p1_tfidf",
    "p1_splade",
    "p2_bm25",
    "p2_tfidf",
    "p3_bm25",
    "p3_tfidf",
    "baseline_qdrant_bm25",
    "hybrid_rrf",
]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Texto de la consulta")
    method: MethodLiteral = Field("p1_bm25", description="Técnica de retrieval")
    size: int = Field(10, ge=1, le=100, description="Cantidad de chunks a devolver")
    scoring: str | None = Field(
        None,
        description=(
            "Variante de scoring. Para BM25: clave de config.BM25_VARIANTS "
            "('default', 'tuned_a/b/c'). Para TF-IDF/SPLADE: clave de "
            "config.RANK_FEATURE_VARIANTS ('linear', 'saturation_pX'). "
            "Para hybrid_rrf: id de un sparse partner válido "
            "(clave de config.HYBRID_SPARSE_VARIANTS). "
            "Si se omite, se usa el default de la técnica."
        ),
    )
    query_id: str | None = Field(
        None,
        description=(
            "Sólo aplica cuando `method=='hybrid_rrf'`: id del benchmark "
            "(`q000`..`qNNN`) cuyo embedding denso pre-computado se usa del "
            "lado vectorial. Si se omite, el lado denso se obtiene embebiendo "
            "el texto de `query` en vivo con Gemini. Se ignora para las demás "
            "técnicas."
        ),
    )


class Hit(BaseModel):
    score: float
    chunk_uuid: str | None = None
    chunk_id: int | None = None
    document_id: str | None = None
    name: str | None = None
    source: str | None = None
    source_type: str | None = None
    rol_number: str | None = None
    bcn_id_norm: int | None = None
    instance_name: str | None = None
    court_specific_name: str | None = None
    date: str | None = None
    publication_date: str | None = None
    url: str | None = None
    content: str | None = None
    char_length: int | None = None
    highlights: dict[str, float] = {}
    # Sólo se setean en respuestas de hybrid_rrf — None para técnicas
    # sparse-only. Permiten que la UI muestre la procedencia del rank
    # (ej. "vino del top-5 denso y top-30 sparse").
    rrf_score: float | None = None
    rank_dense: int | None = None
    rank_sparse: int | None = None


class QueryTerm(BaseModel):
    """Una dimensión del vector esparso, lista para mostrar.

    `term` es la etiqueta legible (término/WordPiece/stem); `key` es la clave
    real usada en el retrieval (igual a `term`, salvo en el baseline Qdrant
    donde es el hash MurmurHash3). `in_query` es False solo cuando la
    dimensión es expansión léxica que el modelo agregó (SPLADE).
    """

    term: str
    key: str
    weight: float
    in_query: bool


class FusionComponents(BaseModel):
    """Metadatos de la fusión RRF (solo se setean para hybrid_rrf)."""

    rrf_k: int
    sparse_method: str
    dense_model: str
    dense_source: str
    query_id: str | None
    fetch_depth: int
    n_dense: int
    n_sparse: int
    n_fused: int


class SearchResponse(BaseModel):
    method: str
    preproc: str
    vectorizer: str
    scoring: str
    query: str
    # Representación histórica (se conserva por compatibilidad).
    query_tokens: list[str]
    query_vector: dict[str, float]
    # Pipeline de introspección de la query (lo que la UI muestra por etapas).
    query_input_tokens: list[str]
    query_input_label: str
    query_terms: list[QueryTerm]
    latency_ms: float
    total: int
    hits: list[Hit]
    # Sólo se setea en respuestas de hybrid_rrf — None para técnicas
    # sparse-only. Permite que la UI muestre el aporte de cada lado.
    fusion_components: FusionComponents | None = None


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Maqui sparse retrieval",
    description="Backend agnóstico al preprocesamiento. La técnica elegida "
    "define el preprocesamiento de la query y el campo de scoring.",
    version="0.4.0",
)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/techniques")
def techniques():
    """Catálogo de técnicas que la UI puede ofrecer.

    Cada técnica declara explícitamente su `scoring_family`:
      - `bm25`: campo `content_pX` con Lucene BM25 nativo. La UI puede
        ofrecer las variantes `tuned_a/b/c` (k1, b distintos).
      - `rank_feature`: campos `tfidf_pX`, `splade_p1` o
        `baseline_qdrant_bm25`. La UI puede ofrecer las variantes
        `linear` y `saturation_pX` de OpenSearch.

    Antes este mapping se inferia heurísticamente en el frontend a partir
    del string `vectorization` (`startsWith('bm25')`). Eso fallaba para
    `baseline_qdrant_bm25` cuya vectorización es nominalmente BM25 pero
    se sirve por `rank_feature` queries en OpenSearch.
    """
    return {
        "techniques": [
            {
                "id": "p1_bm25",
                "preprocessing": "P1 (mínimo, regex)",
                "vectorization": "BM25",
                "scoring_family": "bm25",
                "label": "P1 + BM25",
            },
            {
                "id": "p1_tfidf",
                "preprocessing": "P1 (mínimo, regex)",
                "vectorization": "TF-IDF",
                "scoring_family": "rank_feature",
                "label": "P1 + TF-IDF",
            },
            {
                "id": "p1_splade",
                "preprocessing": "P1 (mínimo) + WordPiece BERT",
                "vectorization": "SPLADE (naver/splade-cocondenser-ensembledistil)",
                "scoring_family": "rank_feature",
                "label": "P1 + SPLADE",
            },
            {
                "id": "p2_bm25",
                "preprocessing": "P2 (SpaCy lematización)",
                "vectorization": "BM25",
                "scoring_family": "bm25",
                "label": "P2 + BM25",
            },
            {
                "id": "p2_tfidf",
                "preprocessing": "P2 (SpaCy lematización)",
                "vectorization": "TF-IDF",
                "scoring_family": "rank_feature",
                "label": "P2 + TF-IDF",
            },
            {
                "id": "p3_bm25",
                "preprocessing": "P3 (Snowball stemming)",
                "vectorization": "BM25",
                "scoring_family": "bm25",
                "label": "P3 + BM25",
            },
            {
                "id": "p3_tfidf",
                "preprocessing": "P3 (Snowball stemming)",
                "vectorization": "TF-IDF",
                "scoring_family": "rank_feature",
                "label": "P3 + TF-IDF",
            },
            {
                "id": "baseline_qdrant_bm25",
                "preprocessing": "Snowball English (default fastembed Qdrant/bm25)",
                "vectorization": "BM25 hasheado (MurmurHash3) servido por rank_features",
                "scoring_family": "rank_feature",
                "label": "Baseline Qdrant BM25",
            },
            {
                "id": "hybrid_rrf",
                "preprocessing": "según sparse partner",
                "vectorization": "RRF (denso Gemini + sparse OpenSearch)",
                "scoring_family": "hybrid",
                "label": "Híbrido RRF (denso + sparse)",
            },
        ]
    }


@app.get("/benchmark-queries")
def benchmark_queries():
    """Catálogo de queries del benchmark, para poblar el dropdown del frontend
    cuando se elige `hybrid_rrf`.

    Lee los `qNNN_*.json` de `config.QUERIES_DIR` y, si está disponible, los
    cruza con el JSON de vectores densos para marcar cuáles tienen embedding
    pre-computado (`has_dense=True`). El frontend filtra a `has_dense=True`
    porque sin embedding no se puede correr el lado denso de la fusión.
    """
    from src import dense_qdrant

    queries_dir = Path(config.QUERIES_DIR)
    available = set(dense_qdrant.available_query_ids())

    items: list[dict] = []
    if queries_dir.is_dir():
        for path in sorted(queries_dir.glob("q*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            qid = data.get("query_id")
            text = data.get("query_text")
            if not qid or not text:
                continue
            items.append(
                {
                    "query_id": qid,
                    "query_text": text,
                    "has_dense": qid in available,
                }
            )

    return {
        "queries": items,
        "total": len(items),
        "with_dense": sum(1 for q in items if q["has_dense"]),
    }


@app.get("/scoring-variants")
def scoring_variants():
    """Catálogo de variantes de scoring que la UI ofrece como segundo
    dropdown. Se separan por familia de vectorización porque son disjuntas:
    BM25 elige entre `content_pX` con distintos (k1, b); TF-IDF y SPLADE
    eligen la función query-time sobre rank_features; hybrid_rrf elige
    qué técnica sparse parea con el lado denso.
    """
    return {
        "bm25": [{"id": vid, "label": v["label"]} for vid, v in config.BM25_VARIANTS.items()],
        "rank_feature": [
            {"id": vid, "label": v["label"]} for vid, v in config.RANK_FEATURE_VARIANTS.items()
        ],
        "hybrid": [
            {"id": vid, "label": v["label"]} for vid, v in config.HYBRID_SPARSE_VARIANTS.items()
        ],
        "defaults": {
            "bm25": config.DEFAULT_BM25_VARIANT,
            "rank_feature": config.DEFAULT_RANK_FEATURE_VARIANT,
            "hybrid": config.DEFAULT_HYBRID_SPARSE,
        },
    }


@app.post("/search", response_model=SearchResponse)
def post_search(req: SearchRequest):
    try:
        result = search.search(
            query=req.query,
            method=req.method,
            size=req.size,
            scoring=req.scoring,
            query_id=req.query_id,
        )
    except GeminiEmbedError as e:
        raise HTTPException(status_code=503, detail=f"gemini embedding: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OpenSearchException as e:
        raise HTTPException(status_code=502, detail=f"opensearch: {e}") from e
    return SearchResponse(**result)


# -----------------------------------------------------------------------------
# Frontend estático
# -----------------------------------------------------------------------------

# El directorio `static/` se monta como volumen en docker-compose.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
