"""
pipeline.py
───────────
Orquesta el pipeline completo:
  1. Carga de chunks
  2. Preprocesamiento (P1, P2, P3) — con caché para no reprocesar
  3. Vectorización según modo seleccionado

Modos disponibles:
  python3 src/pipeline.py              → corre todo
  python3 src/pipeline.py completo     → corre todo
  python3 src/pipeline.py tfidf        → solo TF-IDF (C01, C03, C05)
  python3 src/pipeline.py bm25         → solo BM25   (C02, C04, C06)
  python3 src/pipeline.py qdrant       → solo Qdrant BM25 baseline
  python3 src/pipeline.py splade       → solo SPLADE (C07)
  python3 src/pipeline.py bge          → solo BGE-M3 (C08)

Combinaciones:
  BASELINE  — Qdrant BM25
  C01       — P1 + TF-IDF
  C02       — P1 + BM25
  C03       — P2 + TF-IDF
  C04       — P2 + BM25
  C05       — P3 + TF-IDF
  C06       — P3 + BM25
  C07       — P1 + SPLADE   (GPU recomendada)
  C08       — P1 + BGE-M3   (GPU recomendada)
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from collections import defaultdict

from loader import load_chunks, inspect_chunks
from preprocessors import (
    preprocess_p1,
    preprocess_p1_string,
    preprocess_corpus_p2,
    preprocess_p3,
)
from vectorizers import (
    build_tfidf,
    build_bm25,
    search_bm25,
    load_qdrant_bm25,
    vectorize_qdrant_bm25_corpus,
    load_splade_model,
    vectorize_splade_corpus,
    load_bge_model,
    vectorize_bge_corpus,
)
from sklearn.feature_extraction.text import TfidfVectorizer

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

os.makedirs("outputs/logs", exist_ok=True)
os.makedirs("outputs/vectors", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(
            f"outputs/logs/pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# CACHÉ DE TOKENS
# ─────────────────────────────────────────────────────────────

TOKENS_CACHE = {
    "p1": "outputs/vectors/tokens_p1.json",
    "p2": "outputs/vectors/tokens_p2.json",
    "p3": "outputs/vectors/tokens_p3.json",
}


def load_or_preprocess(texts: list[str]) -> tuple:
    """
    Carga tokens desde caché si existen.
    Si no, preprocesa y guarda para la próxima vez.
    """
    all_cached = all(os.path.exists(p) for p in TOKENS_CACHE.values())

    if all_cached:
        logger.info("Caché encontrado — cargando tokens preprocesados...")
        t0 = time.time()
        tokenized_p1 = json.load(open(TOKENS_CACHE["p1"], encoding="utf-8"))
        tokenized_p2 = json.load(open(TOKENS_CACHE["p2"], encoding="utf-8"))
        tokenized_p3 = json.load(open(TOKENS_CACHE["p3"], encoding="utf-8"))
        logger.info(f"Tokens cargados en {time.time()-t0:.1f}s")
        return tokenized_p1, tokenized_p2, tokenized_p3

    logger.info("No se encontró caché. Preprocesando desde cero...")

    logger.info("Preprocesando P1 (regex mínimo)...")
    t0 = time.time()
    tokenized_p1 = [preprocess_p1(t) for t in texts]
    logger.info(f"P1 listo en {time.time()-t0:.1f}s")

    logger.info("Preprocesando P2 (SpaCy lematización — puede tardar 20-30 min)...")
    t0 = time.time()
    tokenized_p2 = preprocess_corpus_p2(texts)
    logger.info(f"P2 listo en {time.time()-t0:.1f}s")

    logger.info("Preprocesando P3 (NLTK Snowball stemming)...")
    t0 = time.time()
    tokenized_p3 = []
    for i, t in enumerate(texts):
        tokenized_p3.append(preprocess_p3(t))
        if (i + 1) % 5000 == 0:
            logger.info(f"  P3: {i+1}/{len(texts)} procesados")
    logger.info(f"P3 listo en {time.time()-t0:.1f}s")

    logger.info("Guardando tokens en caché...")
    json.dump(tokenized_p1, open(TOKENS_CACHE["p1"], "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(tokenized_p2, open(TOKENS_CACHE["p2"], "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(tokenized_p3, open(TOKENS_CACHE["p3"], "w", encoding="utf-8"), ensure_ascii=False)
    logger.info("Caché guardado.")

    return tokenized_p1, tokenized_p2, tokenized_p3


# ─────────────────────────────────────────────────────────────
# TF-IDF
# ─────────────────────────────────────────────────────────────

def run_tfidf_combination(
    combination_id: str,
    chunks: list[dict],
    tokenized_corpus: list[list[str]],
    output_path: str,
) -> None:
    """Ejecuta TF-IDF y guarda los vectores."""
    logger.info(f"\n{'='*50}")
    logger.info(f"Iniciando {combination_id}")
    logger.info(f"{'='*50}")
    t0 = time.time()

    corpus_strings = [" ".join(tokens) for tokens in tokenized_corpus]

    logger.info("Ajustando TF-IDF...")
    vectorizer = TfidfVectorizer()
    vectorizer.fit(corpus_strings)
    feature_names = vectorizer.get_feature_names_out()
    logger.info(f"Vocabulario: {len(feature_names)} tokens")

    logger.info("Transformando corpus completo...")
    matrix = vectorizer.transform(corpus_strings)

    logger.info("Convirtiendo a formato {token: peso}...")
    cx   = matrix.tocoo()
    rows = defaultdict(dict)
    for i, j, v in zip(cx.row, cx.col, cx.data):
        rows[i][feature_names[j]] = round(float(v), 6)

    results = []
    for i, chunk in enumerate(chunks):
        results.append({
            "chunk_id":  chunk["id"],
            "method":    combination_id,
            "n_nonzero": len(rows[i]),
            "vector":    rows[i],
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    avg = sum(r["n_nonzero"] for r in results) / len(results)
    logger.info(f"Guardado en {output_path}")
    logger.info(f"Promedio no-cero: {avg:.1f} — Tiempo: {time.time()-t0:.1f}s")


# ─────────────────────────────────────────────────────────────
# BM25
# ─────────────────────────────────────────────────────────────

def run_bm25_combination(
    combination_id: str,
    chunks: list[dict],
    tokenized_corpus: list[list[str]],
    tokens_output_path: str,
) -> tuple:
    """Construye índice BM25 y guarda los tokens preprocesados."""
    logger.info(f"\n{'='*50}")
    logger.info(f"Iniciando {combination_id}")
    logger.info(f"{'='*50}")
    t0 = time.time()

    retriever  = build_bm25(tokenized_corpus)
    corpus_ids = [chunk["id"] for chunk in chunks]

    logger.info(f"Guardando tokens en {tokens_output_path}...")
    with open(tokens_output_path, "w", encoding="utf-8") as f:
        json.dump(
            {"method": combination_id, "ids": corpus_ids, "tokens": tokenized_corpus},
            f, ensure_ascii=False, indent=2,
        )

    logger.info(f"Listo. Tiempo: {time.time()-t0:.1f}s")
    return retriever, corpus_ids


# ─────────────────────────────────────────────────────────────
# NEURALES (QDRANT BM25, SPLADE, BGE-M3)
# ─────────────────────────────────────────────────────────────

def run_neural_combination(
    combination_id: str,
    chunks: list[dict],
    vectors: list[dict],
    output_path: str,
) -> None:
    """Guarda vectores generados por modelos neurales o Qdrant BM25."""
    logger.info(f"\n{'='*50}")
    logger.info(f"Guardando {combination_id}")
    logger.info(f"{'='*50}")
    t0 = time.time()

    results = []
    for chunk, vec in zip(chunks, vectors):
        results.append({
            "chunk_id":  chunk["id"],
            "method":    combination_id,
            "n_nonzero": len(vec),
            "vector":    vec,
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    avg = sum(r["n_nonzero"] for r in results) / len(results)
    logger.info(f"Guardado en {output_path}")
    logger.info(f"Promedio no-cero: {avg:.1f} — Tiempo: {time.time()-t0:.1f}s")


# ─────────────────────────────────────────────────────────────
# BÚSQUEDA DE PRUEBA
# ─────────────────────────────────────────────────────────────

def run_test_search(retrievers: dict) -> None:
    """Ejecuta una búsqueda de prueba sobre los índices BM25."""
    logger.info("\n=== Búsqueda de prueba ===")
    query = "el arrendatario deberá restituir el inmueble"

    for nombre, (retriever, ids, preprocessor) in retrievers.items():
        query_tokens = preprocessor(query)
        top = search_bm25(query_tokens, retriever, ids, k=3)
        logger.info(f"\n{nombre}:")
        for chunk_id, score in top:
            logger.info(f"  chunk_id={chunk_id}  score={score:.4f}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    # Leer modo desde argumento
    modo = sys.argv[1] if len(sys.argv) > 1 else "completo"
    modos_validos = {"completo", "tfidf", "bm25", "qdrant", "splade", "bge"}

    if modo not in modos_validos:
        print(f"Modo inválido: '{modo}'")
        print(f"Modos válidos: {modos_validos}")
        sys.exit(1)

    logger.info(f"Iniciando pipeline — modo: {modo}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")

    # ── 1. Cargar chunks ─────────────────────────────────────
    chunks = load_chunks("data/out_payload.txt")
    inspect_chunks(chunks, n=2)
    texts = [c["text"] for c in chunks]

    # ── 2. Preprocesar (con caché) ───────────────────────────
    # Para qdrant/splade/bge solo se necesita P1 string limpio
    # Para tfidf/bm25 se necesitan los tres preprocesadores
    if modo in ("completo", "tfidf", "bm25"):
        tokenized_p1, tokenized_p2, tokenized_p3 = load_or_preprocess(texts)
    else:
        # Solo limpiar texto para modelos que usan string directo
        logger.info("Modo neuronal — solo limpieza P1 necesaria")
        tokenized_p1 = [preprocess_p1(t) for t in texts]

    clean_texts_p1 = [preprocess_p1_string(t) for t in texts]

    # ── 3. TF-IDF ────────────────────────────────────────────
    if modo in ("completo", "tfidf"):
        run_tfidf_combination("C01_P1_TFIDF", chunks, tokenized_p1, "outputs/vectors/c01_p1_tfidf.json")
        run_tfidf_combination("C03_P2_TFIDF", chunks, tokenized_p2, "outputs/vectors/c03_p2_tfidf.json")
        run_tfidf_combination("C05_P3_TFIDF", chunks, tokenized_p3, "outputs/vectors/c05_p3_tfidf.json")

    # ── 4. BM25 ──────────────────────────────────────────────
    bm25_retrievers = {}
    if modo in ("completo", "bm25"):
        r1, ids1 = run_bm25_combination("C02_P1_BM25", chunks, tokenized_p1, "outputs/vectors/c02_p1_bm25_tokens.json")
        r2, ids2 = run_bm25_combination("C04_P2_BM25", chunks, tokenized_p2, "outputs/vectors/c04_p2_bm25_tokens.json")
        r3, ids3 = run_bm25_combination("C06_P3_BM25", chunks, tokenized_p3, "outputs/vectors/c06_p3_bm25_tokens.json")
        bm25_retrievers = {
            "C02_P1_BM25": (r1, ids1, preprocess_p1),
            "C04_P2_BM25": (r2, ids2, preprocess_p1),
            "C06_P3_BM25": (r3, ids3, preprocess_p3),
        }
        run_test_search(bm25_retrievers)

    # ── 5. Qdrant BM25 baseline ──────────────────────────────
    if modo in ("completo", "qdrant"):
        qdrant_model   = load_qdrant_bm25()
        vectors_qdrant = vectorize_qdrant_bm25_corpus(clean_texts_p1, qdrant_model)
        run_neural_combination(
            "BASELINE_QDRANT_BM25", chunks, vectors_qdrant,
            "outputs/vectors/baseline_qdrant_bm25.json"
        )

    # ── 6. SPLADE ────────────────────────────────────────────
    if modo in ("completo", "splade"):
        splade_tok, splade_model, device = load_splade_model()
        logger.info(f"SPLADE corriendo en {'GPU' if device == 'cuda' else 'CPU'}")
        vectors_splade = vectorize_splade_corpus(
            clean_texts_p1, splade_tok, splade_model, device, batch_size=32
        )
        run_neural_combination(
            "C07_P1_SPLADE", chunks, vectors_splade,
            "outputs/vectors/c07_p1_splade.json"
        )

    # ── 7. BGE-M3 ────────────────────────────────────────────
    if modo in ("completo", "bge"):
        bge_model = load_bge_model()
        vectors_bge = vectorize_bge_corpus(
            clean_texts_p1, bge_model, batch_size=32
        )
        run_neural_combination(
            "C08_P1_BGE", chunks, vectors_bge,
            "outputs/vectors/c08_p1_bge.json"
        )

    logger.info("\nPipeline completado exitosamente.")


if __name__ == "__main__":
    main()