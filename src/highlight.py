"""Highlights ponderados por contribución al score.

Para cada hit, devolvemos un dict `{palabra_cruda: score}` donde `score`
refleja cuánto aporta esa palabra al ranking del documento dado la query.
El frontend usa el score para colorear con un gradiente: tonalidad oscura
para palabras que contribuyen mucho, clara para las que contribuyen poco.

Esquema de scoring por técnica:

- BM25 / TF-IDF: `score(palabra) = peso de la query (TF count)` del token
  al que mapea la palabra preprocesada con P1/P2/P3. Casi siempre 1, salvo
  cuando la query repite el mismo término.

- SPLADE: `score(palabra) = suma peso_query[piece]` para cada WordPiece de la
  palabra que esté presente en el vector de la query. Esto incluye piezas
  de continuación (`##cion`, `##es`, etc.) y stopwords retenidos por el
  encoder — la idea es exponer toda la contribución y dejar que el
  gradiente de color comunique la importancia relativa.
"""

from __future__ import annotations

import re

# IMPORTANTE: este import debe ir antes que `from preprocessors import ...`.
# `preprocess_adapter` inserta Vectorizacion/sparse-benchmark/src en sys.path
# como side-effect al cargar; sin esto, el import siguiente falla con
# ModuleNotFoundError porque `preprocessors` vive fuera del PYTHONPATH default.
from . import preprocess_adapter as _preprocess_adapter  # noqa: F401

from nltk.tokenize import word_tokenize  # noqa: E402

from .preprocess_adapter import _spacy_nlp  # type: ignore  # noqa: E402, I001
from preprocessors import (  # type: ignore  # noqa: E402
    clean_pdf_noise,
    stemmer,
    stop_words,
)

_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


def _bump(out: dict[str, float], word: str, score: float) -> None:
    """Acumula score conservando el máximo si la palabra ya estaba.

    Una misma forma cruda puede mapear a un token de query desde más de un
    contexto (ej. `Funciones` y `funciones` con P2 ambos lematizan a
    `función`). En vez de sumar, dejamos el peso máximo — la palabra
    contribuye con ese token, no con N copias del token.
    """
    if score <= 0:
        return
    prev = out.get(word, 0.0)
    if score > prev:
        out[word] = score


def highlight_weights_p1(content: str, query_vector: dict[str, float]) -> dict[str, float]:
    if not content or not query_vector:
        return {}
    cleaned = clean_pdf_noise(content).lower()
    out: dict[str, float] = {}
    for w in set(_WORD_RE.findall(cleaned)):
        if w in query_vector:
            _bump(out, w, float(query_vector[w]))
    return out


def highlight_weights_p2(content: str, query_vector: dict[str, float]) -> dict[str, float]:
    if not content or not query_vector:
        return {}
    cleaned = clean_pdf_noise(content).lower()
    doc = _spacy_nlp(cleaned)
    out: dict[str, float] = {}
    for tok in doc:
        if tok.is_stop or tok.is_punct or tok.is_space:
            continue
        if len(tok.lemma_) <= 1:
            continue
        if tok.lemma_ in query_vector:
            _bump(out, tok.text, float(query_vector[tok.lemma_]))
    return out


def highlight_weights_p3(content: str, query_vector: dict[str, float]) -> dict[str, float]:
    if not content or not query_vector:
        return {}
    cleaned = clean_pdf_noise(content).lower()
    raw = word_tokenize(cleaned, language="spanish")
    out: dict[str, float] = {}
    for t in raw:
        if not t.isalpha() or t in stop_words or len(t) <= 2:
            continue
        s = stemmer.stem(t)
        if s in query_vector:
            _bump(out, t, float(query_vector[s]))
    return out


def highlight_weights_splade(content: str, query_vector: dict[str, float]) -> dict[str, float]:
    """SPLADE: por cada palabra del chunk, score = suma de pesos de los
    WordPieces que matchean el vector de la query.

    No filtramos `##` ni stopwords — el gradiente de color se encarga de
    comunicar la importancia: una palabra que solo matchea via `##cion`
    (peso 1.4) va a aparecer más clara que una que matchea por `legal`
    (peso 1.5) sumado a `##es` (peso 0.5).
    """
    if not content or not query_vector:
        return {}
    from . import splade_encoder

    splade_encoder._ensure_loaded()
    tokenizer = splade_encoder._tokenizer
    assert tokenizer is not None

    cleaned = clean_pdf_noise(content).lower()
    words = set(_WORD_RE.findall(cleaned))
    out: dict[str, float] = {}
    for w in words:
        pieces = tokenizer.tokenize(w)
        score = sum(float(query_vector.get(p, 0.0)) for p in pieces)
        if score > 0:
            out[w] = score
    return out


def compute_highlights(
    content: str, query_vector: dict[str, float], preproc: str, vec: str
) -> dict[str, float]:
    if vec == "splade":
        return highlight_weights_splade(content, query_vector)
    if preproc == "p1":
        return highlight_weights_p1(content, query_vector)
    if preproc == "p2":
        return highlight_weights_p2(content, query_vector)
    if preproc == "p3":
        return highlight_weights_p3(content, query_vector)
    return {}
