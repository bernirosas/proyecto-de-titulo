"""Encoder fastembed para la baseline Qdrant BM25.

Reproduce la encodificación que Qdrant aplica por defecto a documentos y
queries cuando se usa el modelo esparso `Qdrant/bm25`: tokeniza con un
stemmer Snowball (configurable vía `config.BASELINE_QDRANT_BM25_LANGUAGE`,
default `english` — verificado empíricamente sobre el snapshot del
Qdrant del cliente; ver `src/config.py` para el contexto) y hashea cada
stem con MurmurHash3 a un entero de 32 bits. El resultado es un mapa
`{hash_str: peso}` directamente comparable con los vectores extraídos de
la instancia Qdrant del cliente y persistidos en el campo
`baseline_qdrant_bm25` del índice OpenSearch.

Asimetría document/query:
  - Documentos (indexados): el peso es TF × IDF computado por fastembed
    sobre el corpus completo.
  - Queries (este módulo): el peso es TF crudo de cada stem en la query.
    El mismo patrón "asymmetric BM25" que usamos para TF-IDF: documento
    lleva TF·IDF, query lleva TF. La función de combinación rank_feature
    en OpenSearch puntúa solo en función de los pesos del documento, así
    que los pesos de la query funcionan como boost.

Carga del modelo: lazy y singleton. La primera llamada paga el costo de
inicializar el modelo (~1-2s); las siguientes reusan la instancia en
memoria.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter

from . import config

logger = logging.getLogger(__name__)


# Singleton protegido por lock — el modelo fastembed no es thread-safe en
# todas sus versiones, así que serializamos las llamadas a `encode`.
_lock = threading.Lock()
_model: object | None = None


def _ensure_loaded() -> None:
    """Carga el modelo fastembed la primera vez. Idempotente y thread-safe."""
    global _model

    if _model is not None:
        return

    with _lock:
        if _model is not None:
            return

        try:
            from fastembed import SparseTextEmbedding  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "La baseline Qdrant BM25 requiere `fastembed`. "
                "Instale con `pip install fastembed`. "
                f"Detalle: {e}"
            ) from e

        model_name = config.BASELINE_QDRANT_BM25_MODEL
        language = config.BASELINE_QDRANT_BM25_LANGUAGE
        logger.info(
            "[baseline_qdrant_bm25] cargando %s (language=%s) ...",
            model_name,
            language,
        )
        _model = SparseTextEmbedding(model_name=model_name, language=language)
        logger.info("[baseline_qdrant_bm25] modelo cargado")


def encode(text: str) -> dict[str, float]:
    """Devuelve la representación BM25 esparsa de un texto vía fastembed.

    Las claves son los enteros MurmurHash3 (como string, para que sirvan
    de nombre de campo en `rank_features`) de cada stem único de la query.
    Los pesos son la frecuencia (TF) del stem en la query. Si la query es
    muy corta los pesos serán mayormente 1.

    Retorna
    -------
    dict[str, float]
        `{hash_int_str: tf}` con todos los stems no vacíos de la query.
    """
    _ensure_loaded()
    assert _model is not None

    # `query_embed` aplica el pipeline de query (sin IDF, solo TF) y
    # devuelve un generador de SparseEmbedding. Tomamos el primer (y único)
    # elemento. Si por algún motivo está vacío, devolvemos dict vacío.
    embeddings = list(_model.query_embed(text))  # type: ignore[attr-defined]
    if not embeddings:
        return {}

    emb = embeddings[0]
    # fastembed.SparseEmbedding expone `indices` (np.array[int]) y
    # `values` (np.array[float]). Algunas versiones devuelven `int32` y
    # otras `int64`; convertimos a `str` directamente para usar como clave.
    indices = list(emb.indices.tolist())
    values = list(emb.values.tolist())

    # En query-time fastembed entrega TF crudo. Cuando el mismo stem
    # aparece más de una vez puede venir colapsado en una entrada con
    # valor TF (ese es el comportamiento canónico) o, según versión,
    # repetido. Coalecemos por seguridad sumando los valores.
    coalesced: Counter[str] = Counter()
    for idx, val in zip(indices, values, strict=False):
        coalesced[str(idx)] += float(val)
    return dict(coalesced)


def _bm25_worker() -> object | None:
    """Devuelve el worker `Bm25` real que envuelve `SparseTextEmbedding`.

    `SparseTextEmbedding(...)` es una fachada; el objeto que tokeniza,
    stemmea y hashea vive en `.model`. Para distintas versiones de fastembed
    el atributo podría variar, así que probamos `.model` y luego la propia
    instancia, exigiendo que el candidato exponga el pipeline que usamos
    (`tokenizer`, `_stem`, `compute_token_id`). Si nada calza, devolvemos
    None y el caller cae a mostrar hashes.
    """
    for cand in (getattr(_model, "model", None), _model):
        if (
            cand is not None
            and hasattr(cand, "tokenizer")
            and hasattr(cand, "_stem")
            and hasattr(cand, "compute_token_id")
        ):
            return cand
    return None


def encode_with_stems(text: str) -> tuple[dict[str, float], dict[str, str], list[str]]:
    """Como `encode`, pero además reconstruye la capa legible de stems.

    El vector de retrieval usa enteros MurmurHash3 como claves (ilegibles).
    Para la visualización reconstruimos, con el *mismo* pipeline interno de
    fastembed (tokenizer + `_stem` + `compute_token_id`), qué stem originó
    cada hash. Al usar la API propia de fastembed la correspondencia es
    exacta — no una reimplementación que podría divergir del hashing real.

    Retorna
    -------
    (weights, stem_by_hash, ordered_stems)
        - weights: idéntico a `encode` (`{hash_str: tf}`), para el retrieval.
        - stem_by_hash: `{hash_str: stem}` solo para los hashes presentes en
          `weights` (auto-validado: si un stem recomputado no aparece en el
          vector real, no se mapea). Vacío si la API interna no está
          disponible.
        - ordered_stems: los stems de la query en orden, para mostrar la
          etapa de tokenización legible. Vacío si no se pudo reconstruir.
    """
    weights = encode(text)
    if not weights:
        return weights, {}, []

    worker = _bm25_worker()
    if worker is None:
        return weights, {}, []

    try:
        tokens = worker.tokenizer.tokenize(text)  # type: ignore[attr-defined]
        ordered_stems = list(worker._stem(tokens))  # type: ignore[attr-defined]
        stem_by_hash: dict[str, str] = {}
        for stem in ordered_stems:
            h = str(worker.compute_token_id(stem))  # type: ignore[attr-defined]
            if h in weights:
                stem_by_hash.setdefault(h, stem)
    except Exception:  # pragma: no cover - depende de la versión de fastembed
        # Best-effort: cualquier cambio en la API interna degrada a hashes,
        # nunca rompe el retrieval (que ya está resuelto en `weights`).
        logger.debug("[baseline_qdrant_bm25] no se pudo reconstruir stems", exc_info=True)
        return weights, {}, []

    return weights, stem_by_hash, ordered_stems
