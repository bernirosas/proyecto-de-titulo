"""
vectorizers.py
──────────────
Métodos de generación de vectores esparsos para el benchmark.

Fase 1 (CPU, sin GPU):
  - TF-IDF          (sklearn)
  - BM25            (bm25s, variante Lucene)
  - Qdrant BM25     (fastembed — baseline oficial de Qdrant)

Fase 2 (GPU recomendada):
  - SPLADE          (naver/splade-cocondenser-ensembledistil)
  - BGE-M3 sparse   (BAAI/bge-m3)
"""

import logging
import bm25s
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# TF-IDF
# ─────────────────────────────────────────────────────────────

def build_tfidf(tokenized_corpus: list[list[str]]) -> TfidfVectorizer:
    corpus_strings = [" ".join(tokens) for tokens in tokenized_corpus]
    logger.info("Ajustando TF-IDF sobre el corpus completo...")
    vectorizer = TfidfVectorizer()
    vectorizer.fit(corpus_strings)
    vocab_size = len(vectorizer.vocabulary_)
    logger.info(f"TF-IDF ajustado. Vocabulario: {vocab_size} tokens")
    return vectorizer


def vectorize_tfidf(tokens: list[str], vectorizer: TfidfVectorizer) -> dict:
    text = " ".join(tokens)
    vec  = vectorizer.transform([text])
    feature_names = vectorizer.get_feature_names_out()
    cx = vec.tocoo()
    return {
        feature_names[j]: round(float(v), 6)
        for j, v in zip(cx.col, cx.data)
    }


# ─────────────────────────────────────────────────────────────
# BM25
# ─────────────────────────────────────────────────────────────

def build_bm25(tokenized_corpus: list[list[str]]) -> bm25s.BM25:
    logger.info("Construyendo índice BM25 (variante Lucene)...")
    retriever = bm25s.BM25(method="lucene")
    retriever.index(tokenized_corpus)
    logger.info(f"Índice BM25 construido. {len(tokenized_corpus)} chunks indexados.")
    return retriever


def search_bm25(
    query_tokens: list[str],
    retriever: bm25s.BM25,
    corpus_ids: list,
    k: int = 10
) -> list[tuple]:
    results, scores = retriever.retrieve([query_tokens], k=k)
    top_ids    = [corpus_ids[i] for i in results[0]]
    top_scores = scores[0].tolist()
    return list(zip(top_ids, top_scores))


# ─────────────────────────────────────────────────────────────
# BASELINE — Qdrant BM25 (fastembed)
# ─────────────────────────────────────────────────────────────

def load_qdrant_bm25():
    from fastembed import SparseTextEmbedding
    logger.info("Cargando modelo Qdrant/bm25 (FastEmbed)...")
    model = SparseTextEmbedding(model_name="Qdrant/bm25")
    logger.info("Modelo Qdrant BM25 cargado.")
    return model


def vectorize_qdrant_bm25_corpus(texts: list[str], model) -> list[dict]:
    logger.info("Vectorizando corpus con Qdrant BM25...")
    embeddings = list(model.embed(texts))
    results = []
    for i, emb in enumerate(embeddings):
        vec = {
            str(idx): round(float(val), 6)
            for idx, val in zip(emb.indices, emb.values)
        }
        results.append(vec)
        if (i + 1) % 5000 == 0:
            logger.info(f"  Qdrant BM25: {i+1}/{len(texts)} vectorizados")
    logger.info(f"Qdrant BM25 listo. {len(results)} vectores generados.")
    return results


# ─────────────────────────────────────────────────────────────
# SPLADE
# ─────────────────────────────────────────────────────────────

def load_splade_model(model_id: str = "naver/splade-cocondenser-ensembledistil"):
    import torch
    from transformers import AutoTokenizer, AutoModelForMaskedLM
    logger.info(f"Cargando modelo SPLADE: {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model     = AutoModelForMaskedLM.from_pretrained(model_id)
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model  = model.to(device)
    logger.info(f"SPLADE cargado en {device.upper()}.")
    return tokenizer, model, device


def vectorize_splade_corpus(
    texts: list[str],
    tokenizer,
    model,
    device: str,
    batch_size: int = 32
) -> list[dict]:
    import torch
    results = []
    total   = len(texts)
    for i in range(0, total, batch_size):
        batch  = texts[i:i+batch_size]
        tokens = tokenizer(
            batch,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        ).to(device)
        with torch.no_grad():
            output = model(**tokens)
        vecs = torch.max(
            torch.log(1 + torch.relu(output.logits))
            * tokens.attention_mask.unsqueeze(-1),
            dim=1
        )[0]
        for vec in vecs:
            indices = vec.nonzero().squeeze()
            values  = vec[indices]
            result  = {
                tokenizer.decode([idx.item()]): round(val.item(), 6)
                for idx, val in zip(indices, values)
                if val.item() > 0
            }
            results.append(result)
        if (i + batch_size) % 5000 == 0 or i + batch_size >= total:
            logger.info(f"  SPLADE: {min(i+batch_size, total)}/{total} vectorizados")
    return results


# ─────────────────────────────────────────────────────────────
# BGE-M3
# ─────────────────────────────────────────────────────────────

def load_bge_model():
    from FlagEmbedding import BGEM3FlagModel
    logger.info("Cargando modelo BGE-M3...")
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    logger.info("BGE-M3 cargado.")
    return model


def vectorize_bge_corpus(
    texts: list[str],
    model,
    batch_size: int = 32
) -> list[dict]:
    results = []
    total   = len(texts)
    for i in range(0, total, batch_size):
        batch  = texts[i:i+batch_size]
        output = model.encode(
            batch,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False
        )
        for lw in output["lexical_weights"]:
            readable = model.convert_id_to_token(lw)
            results.append({
                token: round(float(peso), 6)
                for token, peso in readable.items()
            })
        if (i + batch_size) % 5000 == 0 or i + batch_size >= total:
            logger.info(f"  BGE-M3: {min(i+batch_size, total)}/{total} vectorizados")
    return results
