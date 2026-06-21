"""Adaptador para el componente denso del híbrido RRF.

El benchmark trabaja con un set fijo de 31 queries cuyos embeddings densos
(Gemini `gemini-embedding-001`, 3072 dim, `task_type=RETRIEVAL_QUERY`) se
pre-computaron offline contra el `.env` del cliente — la API de embeddings
es de pago y no queremos pagar por queries del usuario en el demo. Por eso
el modo híbrido sólo está disponible para los `query_id` del catálogo.

Este módulo encapsula:
  - lectura lazy + cache en memoria del JSON con los vectores
  - llamada a Qdrant (colección `maqui` del cliente) para obtener un
    ranking denso comparable con el sparse de OpenSearch

El payload de Qdrant guarda el UUID del chunk en la clave `id` (extraído
con `client.scroll(with_payload=True)` desde el snapshot original). Eso
nos permite alinear el ranking denso con el sparse (que devuelve
`chunk_uuid` desde OpenSearch) por simple comparación de strings.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from . import clients, config

# Cache simple: la primera invocación lee el archivo; las siguientes reusan
# el dict. 31 vectores × 3072 floats ≈ 1 MB, sobrado para mantenerlos en RAM
# del proceso uvicorn.
_QUERIES_CACHE: dict[str, list[float]] | None = None


def _load_queries() -> dict[str, list[float]]:
    """Carga el JSON con los vectores densos pre-computados de las queries.

    Falla explícito si el archivo no existe o está vacío: sin él, el modo
    híbrido no puede operar y queremos que el error suba al caller (que lo
    traducirá a HTTP 503 o similar) en vez de devolver resultados silenciosos.
    """
    global _QUERIES_CACHE
    if _QUERIES_CACHE is not None:
        return _QUERIES_CACHE

    path = Path(config.QUERIES_DENSE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Genera los embeddings densos con "
            f"`python scripts/benchmark/embed_queries_gemini.py` antes de usar "
            f"hybrid_rrf."
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path} no contiene un dict {{query_id: vector}} válido o está vacío.")

    # Validación rápida: una muestra del primer vector debe tener la dim
    # esperada. Detecta archivos truncados o regenerados con otro modelo.
    sample_key = next(iter(data))
    sample_vec = data[sample_key]
    if not isinstance(sample_vec, list) or len(sample_vec) != 3072:
        raise ValueError(
            f"{path}: dimensión inesperada en {sample_key!r}: "
            f"{len(sample_vec) if isinstance(sample_vec, list) else type(sample_vec).__name__} "
            f"(esperado lista de 3072 floats; revisa que el script usó gemini-embedding-001)."
        )

    _QUERIES_CACHE = data
    return data


def available_query_ids() -> list[str]:
    """IDs de las queries que tienen embedding pre-computado.

    El frontend usa esta lista para poblar el dropdown cuando se elige
    hybrid_rrf. Si el JSON aún no se genera, se devuelve lista vacía
    (sin levantar) — el frontend muestra el aviso correspondiente.
    """
    try:
        return sorted(_load_queries().keys())
    except (FileNotFoundError, ValueError):
        return []


def get_query_vector(query_id: str) -> list[float]:
    """Devuelve el vector denso pre-computado para `query_id`.

    Levanta ValueError con mensaje accionable si el id no está en el JSON:
    eso es lo que el caller traduce a HTTP 400 con la lista de ids válidos.
    """
    queries = _load_queries()
    if query_id not in queries:
        valid = sorted(queries.keys())
        raise ValueError(
            f"query_id {query_id!r} no tiene embedding denso pre-computado. "
            f"Disponibles: {valid[:3]}... ({len(valid)} en total)."
        )
    return queries[query_id]


_LIVE_CACHE: dict[str, list[float]] | None = None
_LIVE_LOCK = threading.Lock()


def _normalize_query(text: str) -> str:
    return " ".join(text.split()).lower()


def _live_cache_key(text: str) -> str:
    digest = hashlib.sha1(_normalize_query(text).encode("utf-8")).hexdigest()
    return f"live_{digest[:16]}"


def _load_live_cache() -> dict[str, list[float]]:
    global _LIVE_CACHE
    if _LIVE_CACHE is not None:
        return _LIVE_CACHE

    path = Path(config.LIVE_DENSE_CACHE_PATH)
    cache: dict[str, list[float]] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        if isinstance(raw, dict):
            for key, entry in raw.items():
                vector = entry.get("vector") if isinstance(entry, dict) else entry
                if isinstance(vector, list) and len(vector) == config.DENSE_DIM:
                    cache[key] = vector

    _LIVE_CACHE = cache
    return cache


def _persist_live_entry(key: str, text: str, vector: list[float]) -> None:
    path = Path(config.LIVE_DENSE_CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LIVE_LOCK:
        stored: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    stored = loaded
            except (json.JSONDecodeError, OSError):
                stored = {}
        stored[key] = {"text": text, "vector": vector}
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def get_or_embed_query_vector(
    query_text: str, query_id: str | None = None
) -> tuple[list[float], str]:
    if query_id:
        return get_query_vector(query_id), "precomputed"

    if not config.HYBRID_LIVE_EMBED_ENABLED:
        raise ValueError(
            "el embedding en vivo está deshabilitado; elige una query del catálogo del benchmark"
        )

    text = (query_text or "").strip()
    if not text:
        raise ValueError("hybrid_rrf requiere una query no vacía o un query_id del catálogo")

    key = _live_cache_key(text)
    cache = _load_live_cache()
    if key in cache:
        return cache[key], "live"

    from . import gemini_embed

    vector = gemini_embed.embed_query(text)
    cache[key] = vector
    _persist_live_entry(key, text, vector)
    return vector, "live"


def search_dense(vector: list[float], top_k: int) -> list[dict[str, Any]]:
    """Recupera los top_k chunks más cercanos al vector vía Qdrant.

    Devuelve una lista ordenada (mejor primero) de dicts con `chunk_uuid`,
    `score` (cosine similarity de Qdrant) y `rank` (1-indexado), lista para
    pasar al fusor RRF. Mantiene el mismo shape que las técnicas sparse
    para que `_reciprocal_rank_fusion()` los trate uniformemente.

    El nombre de la colección y el del vector ('dense') siguen el snapshot
    de Maqui (`extract.py`: `point.vector['dense']`).
    """
    qdrant = clients.get_qdrant()
    # `query_points` es el endpoint moderno (Qdrant v1.10+). Para versiones
    # antiguas el cliente cae a `search()` con la misma semántica.
    response = qdrant.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        using="dense",
        limit=top_k,
        with_payload=True,
        with_vectors=False,
    )

    results: list[dict[str, Any]] = []
    for rank, point in enumerate(response.points, start=1):
        # El UUID del chunk vive en el payload bajo `id` (no en el id de
        # Qdrant, que es otro UUID interno). Esto coincide con cómo Maqui
        # extrajo el snapshot original. Si por alguna razón faltara,
        # fallback al id del punto.
        payload = point.payload or {}
        chunk_uuid = payload.get("id") or payload.get("chunk_uuid") or str(point.id)
        results.append({"chunk_uuid": chunk_uuid, "score": float(point.score), "rank": rank})
    return results
