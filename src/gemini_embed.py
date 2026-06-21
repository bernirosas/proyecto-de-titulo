from __future__ import annotations

import functools

from google import genai
from google.genai import types

from . import config


class GeminiEmbedError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    try:
        return genai.Client()
    except Exception as exc:
        raise GeminiEmbedError(
            "no se pudo inicializar el cliente Gemini; falta GEMINI_API_KEY o GOOGLE_API_KEY"
        ) from exc


def embed_query(text: str) -> list[float]:
    text = text.strip()
    if not text:
        raise ValueError("la query no puede estar vacía")
    if len(text) > config.LIVE_QUERY_MAX_CHARS:
        raise ValueError(
            f"la query excede el máximo de {config.LIVE_QUERY_MAX_CHARS} caracteres "
            f"({len(text)} recibidos)"
        )

    client = get_gemini_client()
    try:
        response = client.models.embed_content(
            model=config.GEMINI_EMBED_MODEL,
            contents=[text],
            config=types.EmbedContentConfig(task_type=config.EMBED_TASK_TYPE_QUERY),
        )
    except Exception as exc:
        raise GeminiEmbedError(f"falló el embedding de la query con Gemini: {exc}") from exc

    embeddings = getattr(response, "embeddings", None)
    if not embeddings:
        raise GeminiEmbedError("Gemini no devolvió embeddings para la query")

    vector = list(embeddings[0].values)
    if len(vector) != config.DENSE_DIM:
        raise GeminiEmbedError(
            f"dimensión inesperada del embedding: {len(vector)} (esperado {config.DENSE_DIM})"
        )
    return vector
