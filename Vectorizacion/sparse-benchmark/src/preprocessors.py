"""
preprocessors.py
────────────────
Tres métodos de preprocesamiento de texto para el benchmark.

P1 — Limpieza básica + tokenización mínima (control)
P2 — SpaCy es_core_news_lg + lematización + stopwords
P3 — NLTK + Snowball Stemmer español + stopwords

Todos comparten el Paso 0 de limpieza de ruido PDF.
Los modelos neurales (SPLADE, BGE-M3) reciben el string
limpio de P1, no tokens procesados.
"""

import re
import logging
import spacy
from nltk.stem import SnowballStemmer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PASO 0 — Limpieza de ruido PDF (común a todos)
# ─────────────────────────────────────────────────────────────

def clean_pdf_noise(text: str) -> str:
    """
    Elimina artefactos de conversión PDF.

    Transformaciones aplicadas:
    - \\xa0  (non-breaking space)  → espacio normal
    - \\u200b (zero-width space)   → eliminado
    - \\ufeff (BOM)                → eliminado
    - \\t     (tab)                → espacio
    - espacios múltiples           → un espacio
    - lowercase                    → normalización de mayúsculas

    Parámetros
    ----------
    text : str
        Texto crudo del chunk

    Retorna
    -------
    str
        Texto limpio en minúsculas
    """
    text = text.replace('\xa0', ' ')   # non-breaking space
    text = text.replace('\u200b', '')  # zero-width space
    text = text.replace('\ufeff', '')  # BOM
    text = text.replace('\t', ' ')     # tab
    text = re.sub(r'\s+', ' ', text)   # espacios múltiples → uno
    return text.strip()


# ─────────────────────────────────────────────────────────────
# P1 — Mínimo (control del benchmark)
# ─────────────────────────────────────────────────────────────

def preprocess_p1(text: str) -> list[str]:
    """
    Preprocesador de control. Solo limpia ruido PDF y tokeniza
    con regex. No aplica stemming, lematización ni stopwords.

    Compatible con TF-IDF, BM25, SPLADE y BGE-M3.
    Para modelos neurales, pasar el string limpio directamente,
    no la lista de tokens.

    Parámetros
    ----------
    text : str
        Texto crudo del chunk

    Retorna
    -------
    list[str]
        Lista de tokens originales (sin reducción morfológica)
    """
    text = clean_pdf_noise(text)
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return tokens


def preprocess_p1_string(text: str) -> str:
    """
    Versión de P1 que retorna string limpio.
    Usar para SPLADE y BGE-M3.
    """
    text = clean_pdf_noise(text)
    return text.lower()


# ─────────────────────────────────────────────────────────────
# P2 — SpaCy + lematización + stopwords
# ─────────────────────────────────────────────────────────────

# Cargar modelo una sola vez al importar el módulo.
# Se deshabilitan parser, senter y ner porque no se usan
# en la lematización, reduciendo el tiempo a ~20-30 min para 75k chunks.
logger.info("Cargando modelo SpaCy es_core_news_lg...")
nlp = spacy.load("es_core_news_lg", disable=["parser", "senter", "ner"])
logger.info("Modelo SpaCy cargado.")


def preprocess_corpus_p2(texts: list[str]) -> list[list[str]]:
    """
    Lematiza y filtra stopwords sobre el corpus completo usando
    spaCy pipe() — procesa en lotes para mayor eficiencia vs.
    llamar preprocess_p2() chunk por chunk.

    Componentes internos activos de es_core_news_lg:
    - tok2vec (CNN, 256 dims): vectoriza tokens con contexto local
    - morphologizer: predice rasgos morfológicos (tiempo, género, número)
    - attribute_ruler: correcciones por reglas
    - lemmatizer: lema según morfología (accuracy 0.966)

    Parámetros
    ----------
    texts : list[str]
        Lista de textos crudos de todos los chunks

    Retorna
    -------
    list[list[str]]
        Lista de listas de lemas (una por chunk)
    """
    cleaned = [clean_pdf_noise(t).lower() for t in texts]
    tokenized = []
    total = len(cleaned)

    for i, doc in enumerate(nlp.pipe(cleaned, batch_size=256, n_process=1)):
        tokens = [
            token.lemma_
            for token in doc
            if not token.is_stop    # elimina "el", "de", "la", "que"...
            and not token.is_punct  # elimina ".", ",", ":", ";"...
            and not token.is_space  # elimina espacios residuales
            and len(token.lemma_) > 1  # elimina tokens de 1 caracter
        ]
        tokenized.append(tokens)

        if (i + 1) % 1000 == 0:
            logger.info(f"  SpaCy P2: {i+1}/{total} chunks procesados")

    return tokenized


# ─────────────────────────────────────────────────────────────
# P3 — NLTK + Snowball Stemmer + stopwords
# ─────────────────────────────────────────────────────────────

stemmer    = SnowballStemmer("spanish")
stop_words = set(stopwords.words("spanish"))


def preprocess_p3(text: str) -> list[str]:
    """
    Preprocesador agresivo. Aplica stemming con Snowball sobre español,
    eliminando stopwords y tokens no alfabéticos.

    Advertencias para texto legal:
    - Números eliminados por isalpha() → pierde artículos, años, roles
    - Colisiones de stems: "arrendamiento" y "arrendatario" → "arrend"
    - Términos en latín pueden ser mal stemmeados

    Parámetros
    ----------
    text : str
        Texto crudo del chunk

    Retorna
    -------
    list[str]
        Lista de stems sin stopwords
    """
    text = clean_pdf_noise(text)
    text = text.lower()
    raw_tokens = word_tokenize(text, language="spanish")
    tokens = [
        stemmer.stem(t)
        for t in raw_tokens
        if t.isalpha()          # elimina números y puntuación
        and t not in stop_words # elimina stopwords
        and len(t) > 2          # elimina tokens muy cortos
    ]
    return tokens
