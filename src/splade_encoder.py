"""Encoder SPLADE para query-time.

Reproduce la inferencia de `naver/splade-cocondenser-ensembledistil` (el modelo
con el que se vectorizó el corpus en Vectorizacion/sparse-benchmark) sobre la
query del usuario, devolviendo un mapa esparso `{token_wordpiece: peso}` que
es directamente comparable con los vectores indexados en `splade_p1`.

Pipeline SPLADE estándar (idéntico a lo que se aplicó offline al corpus):
    1. Limpieza P1 del texto crudo (clean_pdf_noise + lower).
    2. Tokenización WordPiece del modelo (vocab BERT, ~30k tokens).
    3. Forward pass por el MLM head.
    4. Activación: log(1 + ReLU(logits)).
    5. Max-pooling sobre la secuencia (mascarando padding) → vector denso 1xV.
    6. Filtrar las dimensiones con peso > 0 → mapa esparso.

Carga del modelo: lazy y singleton. El primer query SPLADE en una corrida
paga el costo de descargar/cargar (~30s primera vez, ~5-10s en corridas
posteriores). Las queries siguientes reusan el modelo en memoria. La
inferencia en CPU es ~300-700ms por query con max_length=256.
"""

from __future__ import annotations

import logging
import threading

from . import config

logger = logging.getLogger(__name__)


# Singletons protegidos por lock.
_lock = threading.Lock()
_tokenizer: object | None = None
_model: object | None = None
_torch = None


def _ensure_loaded() -> None:
    """Carga modelo + tokenizer la primera vez. Idempotente y thread-safe."""
    global _tokenizer, _model, _torch

    if _model is not None and _tokenizer is not None:
        return

    with _lock:
        if _model is not None and _tokenizer is not None:
            return

        # Imports tardíos: no queremos pagar el costo de torch si nunca se
        # invoca SPLADE.
        try:
            import torch  # type: ignore
            from transformers import AutoModelForMaskedLM, AutoTokenizer  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "SPLADE requiere `transformers` y `torch` instalados. " f"Detalle: {e}"
            ) from e

        model_name = config.SPLADE_MODEL
        logger.info("[splade] cargando %s ...", model_name)
        tok = AutoTokenizer.from_pretrained(model_name)
        mdl = AutoModelForMaskedLM.from_pretrained(model_name)
        mdl.eval()

        _tokenizer = tok
        _model = mdl
        _torch = torch
        logger.info("[splade] modelo cargado (vocab=%d)", len(tok))


def encode(text: str, top_k: int | None = None) -> dict[str, float]:
    """Devuelve la representación SPLADE esparsa de un texto.

    Parámetros
    ----------
    text : str
        Texto crudo de la query (ya limpio con P1, o sin limpiar — el
        tokenizer maneja whitespace; pero por consistencia con la fase de
        indexación se aplica limpieza P1 antes de tokenizar).
    top_k : int, opcional
        Si se especifica, solo se retornan las top-k dimensiones por peso.
        Default: None (todas las dimensiones con peso > 0).

    Retorna
    -------
    dict[str, float]
        {token_wordpiece: peso}. Tokens listos para usar como claves de
        rank_feature queries contra el campo `splade_p1`.
    """
    _ensure_loaded()
    assert _tokenizer is not None and _model is not None and _torch is not None

    # Limpieza P1: usamos clean_pdf_noise y lower del adapter para mantener
    # paridad con la fase de indexación (Vectorizacion/sparse-benchmark/src/
    # preprocessors.py:preprocess_p1_string).
    from .preprocess_adapter import clean_pdf_noise  # type: ignore  # noqa: F401

    cleaned = clean_pdf_noise(text).lower()

    inputs = _tokenizer(
        cleaned,
        return_tensors="pt",
        truncation=True,
        max_length=config.SPLADE_MAX_LENGTH,
        padding=False,
    )

    with _torch.no_grad():
        outputs = _model(**inputs)

    # logits: (batch=1, seq_len, vocab_size).
    logits = outputs.logits
    # Activación SPLADE: log(1 + ReLU(logits)).
    activated = _torch.log1p(_torch.relu(logits))
    # Mask de padding (acá no hay padding pero por completitud).
    mask = inputs["attention_mask"].unsqueeze(-1)  # (1, L, 1)
    activated = activated * mask
    # Max-pooling sobre la secuencia → (vocab_size,)
    weights = activated.max(dim=1).values.squeeze(0)

    # Filtrar > 0.
    nonzero_mask = weights > 0
    nonzero_ids = nonzero_mask.nonzero(as_tuple=False).squeeze(-1).tolist()
    nonzero_weights = weights[nonzero_mask].tolist()

    if top_k is not None and len(nonzero_ids) > top_k:
        # Ordenar por peso descendente y quedarnos con top_k.
        pairs = sorted(zip(nonzero_ids, nonzero_weights, strict=False), key=lambda x: -x[1])
        pairs = pairs[:top_k]
        nonzero_ids = [p[0] for p in pairs]
        nonzero_weights = [p[1] for p in pairs]

    # Convertir IDs a tokens WordPiece. `convert_ids_to_tokens` preserva el
    # prefijo `##` para piezas de continuación, que es lo mismo que se usó
    # como clave en los vectores indexados.
    tokens = _tokenizer.convert_ids_to_tokens(nonzero_ids)
    return {tok: float(w) for tok, w in zip(tokens, nonzero_weights, strict=False)}


def tokenize_query(text: str) -> list[str]:
    """Tokenización WordPiece de la query (la etapa intermedia real).

    Devuelve los WordPieces del input *antes* del pesaje SPLADE, sin los
    tokens especiales `[CLS]`/`[SEP]` (a diferencia del forward pass en
    `encode`, que sí los agrega). Es la pieza que faltaba para distinguir,
    en el vector que devuelve `encode`, qué dimensiones vienen de la query
    original (su clave aparece acá) y cuáles son expansión léxica que el
    modelo agregó (su clave NO aparece acá).

    Es barato: solo tokeniza, no corre el modelo. Reusa la misma limpieza P1
    (`clean_pdf_noise` + lower) que `encode`, para que los WordPieces sean
    exactamente los que entran al forward pass.
    """
    _ensure_loaded()
    assert _tokenizer is not None

    from .preprocess_adapter import clean_pdf_noise  # type: ignore  # noqa: F401

    cleaned = clean_pdf_noise(text).lower()
    return list(_tokenizer.tokenize(cleaned))
