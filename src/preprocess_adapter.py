"""Adapter para reutilizar los preprocesadores definidos en
`Vectorizacion/sparse-benchmark/src/preprocessors.py`.

El objetivo es que la query del usuario reciba *exactamente* el mismo
preprocesamiento que se le aplicó al corpus al generar los vectores que viven
en `vectors/`. Si los preprocesadores son los mismos, los tokens son
comparables y el scoring tiene sentido. Si divergen, el ranking se rompe.

Estrategia: en lugar de duplicar el código, montamos
`Vectorizacion/sparse-benchmark/src` como volumen read-only en el contenedor
(ver docker-compose.yml) y lo agregamos a `sys.path`. Cualquier cambio
upstream se refleja sin necesidad de copiar archivos.

Funciones expuestas:
    preprocess_query(text, method) -> list[str]
        Aplica P1 / P2 / P3 a un único texto (uso en query-time).

Notas sobre P2:
    El módulo de upstream usa `preprocess_corpus_p2(texts)` con `nlp.pipe()`
    pensado para procesar todo el corpus en batch. Para una query única
    usamos `nlp(cleaned_text)` directo, que es más rápido para inputs cortos.
"""

from __future__ import annotations

import os
import sys

# El path se inyecta desde una env var (configurable) o cae a un default.
# En el contenedor Docker el volumen se monta en /app/sparse_benchmark.
_DEFAULT_PATH = "/app/sparse_benchmark"
_VEC_PATH = os.environ.get("VECTORIZACION_PATH", _DEFAULT_PATH)

if _VEC_PATH and _VEC_PATH not in sys.path:
    sys.path.insert(0, _VEC_PATH)

# Imports tardíos: el path tiene que estar configurado primero.
# Si el módulo upstream no está disponible, levantamos un error claro.
try:
    from preprocessors import (  # type: ignore
        clean_pdf_noise,
        preprocess_p1,
        preprocess_p3,
    )
    from preprocessors import (
        nlp as _spacy_nlp,
    )
except ImportError as e:
    raise ImportError(
        f"No se pudo importar los preprocesadores desde {_VEC_PATH}. "
        f"Verifique que VECTORIZACION_PATH apunte a "
        f"Vectorizacion/sparse-benchmark/src y que esté montado en el "
        f"contenedor. Detalle: {e}"
    ) from e


SUPPORTED_METHODS = ("p1", "p2", "p3")


def _preprocess_p2_single(text: str) -> list[str]:
    """Versión single-text de P2 (SpaCy lematización + stopwords).

    El upstream tiene `preprocess_corpus_p2(texts)` pensado para batch con
    `nlp.pipe()`. Acá usamos `nlp(text)` directo para una query individual:
    aplica los mismos componentes (tok2vec, morphologizer, attribute_ruler,
    lemmatizer) y filtra stopwords, puntuación, espacios y tokens de un
    solo carácter — idéntico criterio que el batch.
    """
    cleaned = clean_pdf_noise(text).lower()
    doc = _spacy_nlp(cleaned)
    return [
        tok.lemma_
        for tok in doc
        if not tok.is_stop and not tok.is_punct and not tok.is_space and len(tok.lemma_) > 1
    ]


def preprocess_query(text: str, method: str) -> list[str]:
    """Aplica el preprocesamiento elegido a un texto único (query del usuario).

    Parámetros
    ----------
    text : str
        Texto crudo de la query.
    method : str
        Uno de "p1" (mínimo), "p2" (SpaCy lemmatización), "p3" (Snowball).

    Retorna
    -------
    list[str]
        Lista de tokens procesados, lista para concatenar o vectorizar.
    """
    method = method.lower()
    if method == "p1":
        return preprocess_p1(text)
    if method == "p2":
        return _preprocess_p2_single(text)
    if method == "p3":
        return preprocess_p3(text)
    raise ValueError(
        f"Método de preprocesamiento desconocido: {method!r}. "
        f"Opciones válidas: {SUPPORTED_METHODS}"
    )
