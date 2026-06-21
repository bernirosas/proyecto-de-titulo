"""Lógica de búsqueda sobre `chunks_maqui`.

Soporta 9 técnicas (al día de hoy):
  - 3 BM25 propios       : p1_bm25, p2_bm25, p3_bm25
  - 3 TFIDF propios      : p1_tfidf, p2_tfidf, p3_tfidf
  - 1 SPLADE             : p1_splade
  - 1 BM25 baseline      : baseline_qdrant_bm25 (fastembed `Qdrant/bm25`
                           sobre Snowball English, importado tal cual del
                           Qdrant del cliente).
  - 1 híbrido RRF        : hybrid_rrf (fusiona una sparse de las 8 anteriores
                           con un ranking denso vía Qdrant + Gemini embeddings).

El nombre de la técnica determina:

  1. Cómo se preprocesa la query:
       BM25/TFIDF propios → función P1/P2/P3 del módulo `preprocessors.py`.
       SPLADE             → encoder neuronal `naver/splade-cocondenser-
                            ensembledistil` (ver `src/splade_encoder.py`),
                            que produce su propio vector esparso sobre el
                            vocabulario WordPiece de BERT.
       Baseline Qdrant    → encoder fastembed `Qdrant/bm25` (ver
                            `src/baseline_qdrant_encoder.py`), que tokeniza
                            con Snowball Spanish y hashea con MurmurHash3
                            a enteros de 32 bits.
       Híbrido RRF        → no preprocesa: combina dos rankings ya generados.
                            El lado denso usa embeddings Gemini pre-computados
                            (sólo disponibles para las 31 queries del
                            benchmark, ver `src/dense_qdrant.py`).
  2. Sobre qué campo de OpenSearch se puntúa:
       BM25 propios    → `match` query sobre `content_pX` (texto
                         pre-tokenizado, analyzer whitespace).
       TFIDF           → `bool/should` de `rank_feature.linear` queries
                         sobre `tfidf_pX.<token>`, con boost = TF del
                         token en la query.
       SPLADE          → idem TFIDF pero contra `splade_pX.<token>`, y
                         los boosts son los pesos que devuelve el encoder
                         SPLADE (no TF crudo: el encoder ya pondera y
                         expande léxicamente).
       Baseline Qdrant → idem TFIDF pero contra `baseline_qdrant_bm25.
                         <hash_int>`, con boost = TF del stem en la query.
                         Las claves son los enteros MurmurHash3 que
                         fastembed asigna a cada stem.
       Híbrido RRF     → no puntúa contra ningún campo: fusiona los rankings
                         producidos por el sparse partner (sobre OpenSearch)
                         y el denso (sobre Qdrant) vía Reciprocal Rank Fusion.

Nota sobre el lado-query del TF-IDF: se usa solo TF (no IDF), porque no
tenemos pickled el `TfidfVectorizer` ajustado al corpus. Es el patrón
"asymmetric TF-IDF": el documento lleva TF·IDF, la query lleva TF. La
baseline Qdrant aplica la misma asimetría: el documento lleva TF·IDF
(extraído de Qdrant), la query lleva TF (calculada por `fastembed.
query_embed`).
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from . import clients, config
from .highlight import compute_highlights
from .preprocess_adapter import preprocess_query

_PREPROC_LABELS = {
    "p1": "preprocesamiento P1 · regex + minúscula",
    "p2": "preprocesamiento P2 · lematización (SpaCy)",
    "p3": "preprocesamiento P3 · stemming (Snowball)",
}
_LABEL_WORDPIECE = "tokenización WordPiece (BERT)"
_LABEL_STEMS = "stems (Snowball, fastembed)"
_LABEL_HASHES_FALLBACK = "hashes MurmurHash3 (stems no disponibles)"
_LABEL_HYBRID_RRF = "fusión RRF (denso + sparse)"


def _lexical_terms(query_vector: dict[str, float]) -> list[dict]:
    """Términos del vector para técnicas léxicas (BM25/TF-IDF/baseline).

    No hay expansión: cada dimensión del vector proviene de un término de la
    query, así que `in_query` es siempre True. `term` y `key` coinciden."""
    return [{"term": t, "key": t, "weight": w, "in_query": True} for t, w in query_vector.items()]


# Campos que devolvemos al cliente. Mantiene el response liviano y predecible.
_RETURN_FIELDS = [
    "chunk_uuid",
    "chunk_id",
    "document_id",
    "name",
    "source",
    "source_type",
    "rol_number",
    "bcn_id_norm",
    "instance_name",
    "court_specific_name",
    "date",
    "publication_date",
    "url",
    "content",
    "char_length",
]


def _split_method(method: str) -> tuple[str, str]:
    """Parsea 'pN_<vec>' → ('pN', '<vec>'). Valida contra el catálogo.

    Las técnicas con formato no-canónico (p. ej. `baseline_qdrant_bm25`,
    `hybrid_rrf`) no deben pasar por aquí: el caller debe ramificar antes
    y manejarlas en su propio camino. Si llegan, se levanta ValueError
    para no devolver una tupla con preproc inválido.
    """
    method = method.lower()
    if method not in config.TECHNIQUES:
        raise ValueError(f"Técnica desconocida: {method!r}. " f"Opciones: {config.TECHNIQUES}")
    parts = method.split("_", 1)
    if len(parts) != 2 or not parts[0].startswith("p") or len(parts[0]) != 2:
        raise ValueError(
            f"_split_method no acepta técnicas no-canónicas: {method!r}. "
            "El caller debe ramificar antes."
        )
    return parts[0], parts[1]


def _resolve_bm25_variant(scoring: str) -> dict:
    if scoring not in config.BM25_VARIANTS:
        raise ValueError(
            f"Variante de scoring BM25 desconocida: {scoring!r}. "
            f"Opciones: {tuple(config.BM25_VARIANTS)}"
        )
    return config.BM25_VARIANTS[scoring]


def _resolve_rank_feature_variant(scoring: str) -> dict:
    if scoring not in config.RANK_FEATURE_VARIANTS:
        raise ValueError(
            f"Variante de scoring rank_feature desconocida: {scoring!r}. "
            f"Opciones: {tuple(config.RANK_FEATURE_VARIANTS)}"
        )
    return config.RANK_FEATURE_VARIANTS[scoring]


def _build_bm25_body(query_tokens: list[str], preproc: str, size: int, scoring: str) -> dict:
    """Match query sobre content_pX[suffix].

    El sufijo del campo se determina por la variante de scoring elegida
    (ver `config.BM25_VARIANTS`): default → `content_pX`, tuned_a/b/c →
    `content_pX_a/b/c`. Cada campo hermano usa una similarity Lucene
    distinta (k1, b distintos), declarada en `schema.CHUNKS_MAPPING`.
    """
    variant = _resolve_bm25_variant(scoring)
    field = f"content_{preproc}{variant['field_suffix']}"
    joined = " ".join(query_tokens)
    if not joined:
        return {"size": 0, "query": {"match_none": {}}, "_source": _RETURN_FIELDS}
    return {
        "size": size,
        "query": {"match": {field: joined}},
        "_source": _RETURN_FIELDS,
    }


def _build_tfidf_body(query_tokens: list[str], preproc: str, size: int, scoring: str) -> dict:
    """bool/should de rank_feature queries sobre tfidf_pX.<token>.

    Boost = TF del token en la query (asymmetric TFIDF). La función de
    combinación (linear/saturation/...) la define `scoring` vía
    `config.RANK_FEATURE_VARIANTS`.
    """
    if not query_tokens:
        return {"size": 0, "query": {"match_none": {}}, "_source": _RETURN_FIELDS}

    variant = _resolve_rank_feature_variant(scoring)
    field = f"tfidf_{preproc}"
    tf = Counter(query_tokens)

    should = [
        {
            "rank_feature": {
                "field": f"{field}.{token}",
                variant["function"]: dict(variant["params"]),
                "boost": float(count),
            }
        }
        for token, count in tf.items()
    ]
    return {
        "size": size,
        "query": {"bool": {"should": should, "minimum_should_match": 1}},
        "_source": _RETURN_FIELDS,
    }


def _build_baseline_qdrant_bm25_body(
    query_weights: dict[str, float], size: int, scoring: str
) -> dict:
    """bool/should de rank_feature queries sobre baseline_qdrant_bm25.<hash>.

    `query_weights` viene del encoder fastembed (`Qdrant/bm25`): claves
    son enteros MurmurHash3 como string, valores son TF crudo del stem
    en la query. Boost = TF, mismo patrón asymmetric que tfidf/splade.
    """
    if not query_weights:
        return {"size": 0, "query": {"match_none": {}}, "_source": _RETURN_FIELDS}

    variant = _resolve_rank_feature_variant(scoring)
    field = "baseline_qdrant_bm25"
    should = [
        {
            "rank_feature": {
                "field": f"{field}.{token}",
                variant["function"]: dict(variant["params"]),
                "boost": float(weight),
            }
        }
        for token, weight in query_weights.items()
        if weight > 0
    ]
    return {
        "size": size,
        "query": {"bool": {"should": should, "minimum_should_match": 1}},
        "_source": _RETURN_FIELDS,
    }


def _build_splade_body(
    query_weights: dict[str, float], preproc: str, size: int, scoring: str
) -> dict:
    """bool/should de rank_feature queries sobre splade_pX.<token>.

    A diferencia de TFIDF, los boosts NO son TF crudo sino los pesos que
    devuelve el encoder SPLADE. La función de combinación se elige igual
    que en TFIDF vía `config.RANK_FEATURE_VARIANTS`.
    """
    if not query_weights:
        return {"size": 0, "query": {"match_none": {}}, "_source": _RETURN_FIELDS}

    variant = _resolve_rank_feature_variant(scoring)
    field = f"splade_{preproc}"
    should = [
        {
            "rank_feature": {
                "field": f"{field}.{token}",
                variant["function"]: dict(variant["params"]),
                "boost": float(weight),
            }
        }
        for token, weight in query_weights.items()
        if weight > 0
    ]
    return {
        "size": size,
        "query": {"bool": {"should": should, "minimum_should_match": 1}},
        "_source": _RETURN_FIELDS,
    }


def _format_hits(response: dict) -> dict:
    hits = response.get("hits", {})
    return {
        "total": hits.get("total", {}).get("value", 0),
        "hits": [{"score": h["_score"], **(h.get("_source") or {})} for h in hits.get("hits", [])],
    }


def _default_scoring_for(vec: str) -> str:
    if vec == "bm25":
        return config.DEFAULT_BM25_VARIANT
    return config.DEFAULT_RANK_FEATURE_VARIANT


def _build_sparse_intro(query: str, method: str, size: int, scoring: str | None) -> dict[str, Any]:
    """Construye body de OpenSearch + introspección de la query para una técnica sparse.

    Devuelve un dict con:
      - body: dict para `os_client.search()`
      - preproc, vectorizer, scoring: identidades de la técnica resuelta
      - tokens: tokens internos del vector (clave en el espacio del vectorizador)
      - query_vector: dict {clave: peso} efectivo
      - input_tokens, input_label: lo que la UI muestra como etapa-2 del pipeline
      - query_terms: lista lista-para-renderear con `term`, `key`, `weight`, `in_query`

    Se extrajo de `search()` para que el modo híbrido pueda reutilizar el
    cómputo del body sparse sin duplicar la lógica de cada vectorizador.
    """
    if method == "baseline_qdrant_bm25":
        from . import baseline_qdrant_encoder

        scoring = scoring or config.DEFAULT_RANK_FEATURE_VARIANT
        weights, stem_by_hash, ordered_stems = baseline_qdrant_encoder.encode_with_stems(query)
        tokens = list(weights.keys())
        query_vector = weights
        body = _build_baseline_qdrant_bm25_body(weights, size, scoring)
        preproc = "qdrant"
        vec = "baseline_bm25"
        if ordered_stems:
            input_tokens = ordered_stems
            input_label = _LABEL_STEMS
        else:
            input_tokens = tokens
            input_label = _LABEL_HASHES_FALLBACK
        query_terms = [
            {"term": stem_by_hash.get(k, k), "key": k, "weight": w, "in_query": True}
            for k, w in weights.items()
        ]
        return {
            "body": body,
            "preproc": preproc,
            "vectorizer": vec,
            "scoring": scoring,
            "tokens": tokens,
            "query_vector": query_vector,
            "input_tokens": input_tokens,
            "input_label": input_label,
            "query_terms": query_terms,
        }

    preproc, vec = _split_method(method)
    scoring = scoring or _default_scoring_for(vec)
    tokens: list[str] = []
    query_vector: dict[str, float] = {}

    if vec == "bm25":
        tokens = preprocess_query(query, preproc)
        query_vector = {tok: float(c) for tok, c in Counter(tokens).items()}
        body = _build_bm25_body(tokens, preproc, size, scoring)
        input_tokens = tokens
        input_label = _PREPROC_LABELS[preproc]
        query_terms = _lexical_terms(query_vector)
    elif vec == "tfidf":
        tokens = preprocess_query(query, preproc)
        query_vector = {tok: float(c) for tok, c in Counter(tokens).items()}
        body = _build_tfidf_body(tokens, preproc, size, scoring)
        input_tokens = tokens
        input_label = _PREPROC_LABELS[preproc]
        query_terms = _lexical_terms(query_vector)
    elif vec == "splade":
        from . import splade_encoder

        splade_weights = splade_encoder.encode(query, top_k=128)
        tokens = list(splade_weights.keys())
        query_vector = splade_weights
        body = _build_splade_body(splade_weights, preproc, size, scoring)
        input_tokens = splade_encoder.tokenize_query(query)
        input_label = _LABEL_WORDPIECE
        wp_set = set(input_tokens)
        query_terms = [
            {"term": t, "key": t, "weight": w, "in_query": t in wp_set}
            for t, w in splade_weights.items()
        ]
    else:
        raise ValueError(f"Vectorización desconocida: {vec!r}")

    return {
        "body": body,
        "preproc": preproc,
        "vectorizer": vec,
        "scoring": scoring,
        "tokens": tokens,
        "query_vector": query_vector,
        "input_tokens": input_tokens,
        "input_label": input_label,
        "query_terms": query_terms,
    }


def _reciprocal_rank_fusion(
    rankings: list[list[dict[str, Any]]],
    k: int = config.RRF_K,
) -> list[dict[str, Any]]:
    """Implementación canónica de Reciprocal Rank Fusion (Cormack et al. 2009).

    Para cada documento, su score fusionado es la suma de `1/(k + rank_r)`
    sobre las listas que lo contienen (las listas en las que no aparece
    contribuyen 0, no se penaliza explícitamente).

    Cada elemento de `rankings` es una lista ordenada de dicts con al menos
    `chunk_uuid` y `rank` (1-indexado). El output es la lista fusionada,
    ordenada por score descendente, con metadatos por documento:

        {
            "chunk_uuid": str,
            "rrf_score": float,
            "ranks": [rank_dense, rank_sparse, ...],  # None si no aparece
            "scores": [score_dense, score_sparse, ...],  # opcional
        }

    El orden posicional en `rankings` se preserva: rankings[0] → ranks[0],
    etc. Eso permite que el caller sepa qué lista aportó qué rank sin
    inspeccionar más metadatos.

    Tie-breaking por `chunk_uuid` ascendente para garantizar determinismo
    cuando dos chunks empatan exactamente en RRF score (raro pero posible
    si ambos aparecen en simétricas posiciones).
    """
    if k < 0:
        raise ValueError(f"k debe ser >= 0 (Cormack default = 60); recibido {k!r}")

    n = len(rankings)
    accum: dict[str, dict[str, Any]] = {}
    for list_idx, ranking in enumerate(rankings):
        for entry in ranking:
            uuid = entry["chunk_uuid"]
            rank = entry["rank"]
            score = entry.get("score")
            cell = accum.setdefault(
                uuid,
                {
                    "chunk_uuid": uuid,
                    "rrf_score": 0.0,
                    "ranks": [None] * n,
                    "scores": [None] * n,
                },
            )
            cell["rrf_score"] += 1.0 / (k + rank)
            cell["ranks"][list_idx] = rank
            cell["scores"][list_idx] = score

    return sorted(accum.values(), key=lambda x: (-x["rrf_score"], x["chunk_uuid"]))


def _fetch_sources_by_uuid(uuids: list[str]) -> dict[str, dict]:
    """Resuelve `_source` para una lista de chunk_uuid en una sola query OS.

    Devuelve un dict `{chunk_uuid: source_dict}`. Los UUIDs que OpenSearch
    no encuentre simplemente no aparecen en el dict; el caller decide cómo
    representar esa ausencia (típicamente: skippear el hit, indicando que
    Qdrant tiene chunks que OS no tiene).
    """
    if not uuids:
        return {}
    os_client = clients.get_opensearch()
    body = {
        "size": len(uuids),
        "query": {"terms": {"chunk_uuid.keyword": uuids}},
        "_source": _RETURN_FIELDS,
    }
    resp = os_client.search(index=config.INDEX_CHUNKS, body=body)
    out: dict[str, dict] = {}
    for hit in resp.get("hits", {}).get("hits", []):
        src = hit.get("_source") or {}
        uuid = src.get("chunk_uuid")
        if uuid:
            out[uuid] = src
    return out


def _hybrid_rrf_search(
    query: str,
    query_id: str | None,
    size: int,
    sparse_method: str | None,
) -> dict:
    """Ejecuta hybrid_rrf: combina ranking sparse de OpenSearch + denso de Qdrant.

    El `scoring` que recibe el endpoint (renombrado a `sparse_method` aquí
    para mayor claridad) determina qué técnica sparse parea con el lado
    denso. Default: `config.DEFAULT_HYBRID_SPARSE`.

    Requiere `query_id` porque los embeddings densos se pre-computaron
    offline para los 31 queries del benchmark (los costos de la API
    Gemini no permiten embedding ad-hoc en el demo).
    """
    from . import dense_qdrant

    sparse_method = sparse_method or config.DEFAULT_HYBRID_SPARSE
    if sparse_method not in config.HYBRID_SPARSE_VARIANTS:
        raise ValueError(
            f"sparse_method {sparse_method!r} no es un socio sparse válido para hybrid_rrf. "
            f"Opciones: {tuple(config.HYBRID_SPARSE_VARIANTS)}"
        )

    fetch_depth = max(size * config.RRF_FETCH_MULTIPLIER, config.RRF_FETCH_MIN)

    # ---- Lado sparse: OpenSearch
    sparse_intro = _build_sparse_intro(query, sparse_method, fetch_depth, scoring=None)
    os_client = clients.get_opensearch()
    sparse_resp = os_client.search(index=config.INDEX_CHUNKS, body=sparse_intro["body"])
    sparse_hits_raw = sparse_resp.get("hits", {}).get("hits", [])
    sparse_ranking = []
    sparse_source_by_uuid: dict[str, dict] = {}
    for rank, h in enumerate(sparse_hits_raw, start=1):
        src = h.get("_source") or {}
        uuid = src.get("chunk_uuid")
        if not uuid:
            continue
        sparse_ranking.append({"chunk_uuid": uuid, "rank": rank, "score": h["_score"]})
        sparse_source_by_uuid[uuid] = src

    # ---- Lado denso: Qdrant con embedding pre-computado o embebido en vivo
    query_vector, dense_source = dense_qdrant.get_or_embed_query_vector(query, query_id)
    dense_ranking = dense_qdrant.search_dense(query_vector, top_k=fetch_depth)

    # ---- Fusión RRF
    # Orden de las listas en el output → posición 0 = denso, 1 = sparse.
    # Mantenemos ese contrato porque el response de la API lo declara
    # explícito en `fusion_components`.
    fused = _reciprocal_rank_fusion([dense_ranking, sparse_ranking], k=config.RRF_K)
    top_fused = fused[:size]

    # ---- Resolver _source para los chunks que vinieron sólo del lado denso
    missing_uuids = [
        f["chunk_uuid"] for f in top_fused if f["chunk_uuid"] not in sparse_source_by_uuid
    ]
    extra_sources = _fetch_sources_by_uuid(missing_uuids)

    # ---- Armar el response final, preservando el orden de la fusión
    hits: list[dict[str, Any]] = []
    for f in top_fused:
        uuid = f["chunk_uuid"]
        src = sparse_source_by_uuid.get(uuid) or extra_sources.get(uuid)
        if not src:
            # Qdrant tiene un chunk que OpenSearch no — situación rara
            # (drift entre snapshots). Lo skippeamos en silencio para no
            # romper el top-k.
            continue
        hits.append(
            {
                "score": f["rrf_score"],
                "rrf_score": f["rrf_score"],
                "rank_dense": f["ranks"][0],
                "rank_sparse": f["ranks"][1],
                **src,
            }
        )

    # Highlights se calculan sobre el lado sparse (la única descomposición
    # del query que tenemos en términos legibles). En la UI esto pinta los
    # tokens del sparse partner; el aporte denso queda implícito en el rank.
    for hit in hits:
        hit["highlights"] = compute_highlights(
            hit.get("content") or "",
            sparse_intro["query_vector"],
            sparse_intro["preproc"],
            sparse_intro["vectorizer"],
        )

    return {
        "hits": hits,
        "total": len(hits),
        "sparse_intro": sparse_intro,
        "sparse_method": sparse_method,
        "dense_source": dense_source,
        "fetch_depth": fetch_depth,
        "n_dense": len(dense_ranking),
        "n_sparse": len(sparse_ranking),
        "n_fused": len(fused),
    }


def search(
    query: str,
    method: str,
    size: int = 10,
    scoring: str | None = None,
    query_id: str | None = None,
) -> dict:
    """Punto de entrada único para FastAPI.

    Parameters
    ----------
    scoring : str, opcional
        Variante de la función de scoring. Para BM25 una clave de
        `config.BM25_VARIANTS` (default `"default"`); para TFIDF/SPLADE una
        clave de `config.RANK_FEATURE_VARIANTS` (default `"linear"`); para
        `hybrid_rrf` el id de un sparse partner válido (clave de
        `config.HYBRID_SPARSE_VARIANTS`, default `DEFAULT_HYBRID_SPARSE`).
        Si es `None` o vacío, se aplica el default según la técnica.
    query_id : str, opcional
        Sólo aplica cuando `method == "hybrid_rrf"`: identificador del
        benchmark (`q000`..`qNNN`) que indica qué embedding denso pre-
        computado usar como representación de la query del lado vectorial.
        Para todas las demás técnicas se ignora.

    Returns
    -------
    dict con:
        method, query, preproc, vectorizer, scoring,
        query_tokens, query_vector,
        query_input_tokens, query_input_label, query_terms,
        latency_ms, total, hits

    Sobre la introspección de la query (lo que la UI muestra como pipeline):
        - query_tokens / query_vector: representación histórica (términos que
          forman el vector y `{clave: peso}`). Se conservan por compatibilidad.
        - query_input_tokens / query_input_label: la etapa 2 (cómo la técnica
          descompone la query). En BM25/TFIDF es la SALIDA del preprocesamiento
          (difiere entre P1/P2/P3 — es lo que permite compararlos); en SPLADE
          son los WordPieces de la query; en el baseline Qdrant, los stems;
          en hybrid_rrf, los del sparse partner (el lado denso no se
          descompone en términos legibles).
        - query_terms: el vector listo para mostrar, con `term` legible, `key`
          (la clave real, p. ej. el hash en Qdrant), `weight` e `in_query`
          (False = expansión léxica del modelo, solo posible en SPLADE).
    """
    # Latencia de extremo a extremo de la busqueda (preproc/encoder + I/O).
    _t0 = time.perf_counter()

    # ---- Modo híbrido: dispatching independiente del flujo sparse-only
    if method == "hybrid_rrf":
        result = _hybrid_rrf_search(query, query_id, size, scoring)
        latency_ms = round((time.perf_counter() - _t0) * 1000, 1)
        intro = result["sparse_intro"]
        return {
            "method": method,
            "preproc": intro["preproc"],
            "vectorizer": "hybrid_rrf",
            "scoring": result["sparse_method"],
            "query": query,
            "query_tokens": intro["tokens"],
            "query_vector": intro["query_vector"],
            "query_input_tokens": intro["input_tokens"],
            "query_input_label": _LABEL_HYBRID_RRF,
            "query_terms": intro["query_terms"],
            "latency_ms": latency_ms,
            "total": result["total"],
            "hits": result["hits"],
            "fusion_components": {
                "rrf_k": config.RRF_K,
                "sparse_method": result["sparse_method"],
                "dense_model": config.GEMINI_EMBED_MODEL,
                "dense_source": result["dense_source"],
                "query_id": query_id,
                "fetch_depth": result["fetch_depth"],
                "n_dense": result["n_dense"],
                "n_sparse": result["n_sparse"],
                "n_fused": result["n_fused"],
            },
        }

    # ---- Sparse-only (las 8 técnicas pre-existentes)
    intro = _build_sparse_intro(query, method, size, scoring)
    os_client = clients.get_opensearch()
    resp = os_client.search(index=config.INDEX_CHUNKS, body=intro["body"])
    formatted = _format_hits(resp)

    # Cierre del timer ANTES de los highlights: éstos son post-procesamiento
    # para colorear el frontend, no parte del retrieval. Incluirlos en el
    # cómputo inflaba la latencia de forma engañosa — especialmente para
    # SPLADE, donde compute_highlights vuelve a cargar el tokenizer del
    # encoder neuronal por su cuenta. La latencia ahora mide lo que el
    # nombre sugiere: preproc/encoder + I/O a OpenSearch.
    latency_ms = round((time.perf_counter() - _t0) * 1000, 1)

    for hit in formatted["hits"]:
        hit["highlights"] = compute_highlights(
            hit.get("content") or "",
            intro["query_vector"],
            intro["preproc"],
            intro["vectorizer"],
        )

    return {
        "method": method,
        "preproc": intro["preproc"],
        "vectorizer": intro["vectorizer"],
        "scoring": intro["scoring"],
        "query": query,
        "query_tokens": intro["tokens"],
        "query_vector": intro["query_vector"],
        "query_input_tokens": intro["input_tokens"],
        "query_input_label": intro["input_label"],
        "query_terms": intro["query_terms"],
        "latency_ms": latency_ms,
        **formatted,
    }
