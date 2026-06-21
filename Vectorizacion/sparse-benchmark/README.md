# Sparse Benchmark — Preprocesamiento y Vectorización

Pipeline de preprocesamiento y generación de vectores esparsos para el benchmark de búsqueda del corpus legal de maqui.ai.

## Estructura

```
sparse-benchmark/
├── data/
│   └── out_payload.txt          ← archivo de Carlos (no modificar)
├── src/
│   ├── loader.py                ← carga chunks desde out_payload.txt
│   ├── preprocessors.py         ← P1, P2, P3
│   ├── vectorizers.py           ← TF-IDF, BM25 (luego SPLADE, BGE-M3)
│   └── pipeline.py              ← script principal
├── outputs/
│   ├── vectors/                 ← vectores TF-IDF y tokens BM25 por combinación
│   └── logs/                    ← logs del pipeline
├── notebooks/
│   └── exploration.ipynb        ← inspección de datos
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
python -m spacy download es_core_news_lg
python -c "import nltk; nltk.download('stopwords'); nltk.download('punkt_tab')"
```

## Datos

Colocar `out_payload.txt` en `data/`.

## Ejecutar

```bash
cd src
python pipeline.py
```

## Combinaciones Fase 1

| ID  | Preprocesador | Vectorización | Output |
|-----|--------------|--------------|--------|
| C01 | P1 mínimo    | TF-IDF       | c01_p1_tfidf.json |
| C02 | P1 mínimo    | BM25         | c02_p1_bm25_tokens.json |
| C03 | P2 SpaCy     | TF-IDF       | c03_p2_tfidf.json |
| C04 | P2 SpaCy     | BM25         | c04_p2_bm25_tokens.json |
| C05 | P3 Snowball  | TF-IDF       | c05_p3_tfidf.json |
| C06 | P3 Snowball  | BM25         | c06_p3_bm25_tokens.json |

## Outputs

**TF-IDF** — JSON con vector por chunk:
```json
[
  {
    "chunk_id": "a3f2b1c4-...",
    "method": "C01_P1_TFIDF",
    "n_nonzero": 8,
    "vector": {"arrendatario": 0.4123, "restituir": 0.4401}
  }
]
```

**BM25** — JSON con tokens preprocesados para reconstruir el índice:
```json
{
  "method": "C02_P1_BM25",
  "ids": ["a3f2b1c4-...", ...],
  "tokens": [["arrendatario", "restituir", ...], ...]
}
```

## Tiempos estimados

| Paso | Tiempo |
|------|--------|
| Carga de chunks | ~1 min |
| P1 (regex) | ~2 min |
| P2 (SpaCy pipe) | ~20–30 min |
| P3 (Snowball) | ~3 min |
| TF-IDF × 3 | ~5 min |
| BM25 × 3 | ~3 min |
| **Total** | **~35–45 min** |

## Fase 2 (próximamente)

Agregar SPLADE y BGE-M3 en `vectorizers.py`.
