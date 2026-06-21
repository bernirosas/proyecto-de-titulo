import os

# --- OpenSearch ---------------------------------------------------------------
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_USE_SSL = os.getenv("OPENSEARCH_USE_SSL", "false").lower() == "true"

# --- Qdrant -------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "maqui")

# --- Índices ------------------------------------------------------------------
INDEX_CHUNKS = "chunks_maqui"
# Índice operacional (no parte del MER): guarda el top-k crudo por
# (query_id, technique_name) tras correr scripts/benchmark/retrieve_for_query.py.
# Sirve de evidencia de qué retornó cada técnica antes de que se compute
# cualquier métrica de calidad con ground_truth.
INDEX_RETRIEVAL_RESULTS = "retrieval_results"

# --- Ingestión ----------------------------------------------------------------
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "250"))

# --- Vectores pre-computados --------------------------------------------------
# Carpeta con los archivos generados por
# Vectorizacion/sparse-benchmark/src/pipeline.py:
#   c01_p1_tfidf.json, c02_p1_bm25_tokens.json,
#   c03_p2_tfidf.json, c04_p2_bm25_tokens.json,
#   c05_p3_tfidf.json, c06_p3_bm25_tokens.json,
#   c07_p1_splade.json
VECTORS_DIR = os.getenv("VECTORS_DIR", "/app/vectors")

# Nombres canónicos de los archivos (mantienen el esquema de la fase de
# vectorización para que la trazabilidad sea directa). La entrada
# `baseline_qdrant_bm25` no sigue el patrón cXX_pY_<vec> porque no fue
# generada por nuestra pipeline: son los vectores que el cliente ya tenía
# en su instancia Qdrant, extraídos con `client.scroll()`. Se incluyen
# como baseline para comparar contra las técnicas que sí construimos.
VECTOR_FILES = {
    "tfidf_p1": "c01_p1_tfidf.json",
    "bm25_p1": "c02_p1_bm25_tokens.json",
    "tfidf_p2": "c03_p2_tfidf.json",
    "bm25_p2": "c04_p2_bm25_tokens.json",
    "tfidf_p3": "c05_p3_tfidf.json",
    "bm25_p3": "c06_p3_bm25_tokens.json",
    "splade_p1": "c07_p1_splade.json",
    "baseline_qdrant_bm25": "baseline_qdrant_bm25.json",
}

# --- Técnicas soportadas ------------------------------------------------------
# (preprocessing, vectorization). Cada entrada tiene vectores en VECTORS_DIR.
# `baseline_qdrant_bm25` es la única que rompe el patrón pX_<vec>: representa
# el BM25 esparso que el cliente tiene en Qdrant (fastembed `Qdrant/bm25`
# sobre Snowball Spanish, con MurmurHash3 como esquema de claves). Sirve de
# baseline contra el cual comparar nuestras tres BM25 (p1/p2/p3) y nuestras
# tres TF-IDF, además de SPLADE.
# BGEM3 queda para una etapa posterior cuando llegue su archivo.
TECHNIQUES = (
    "p1_bm25",
    "p1_tfidf",
    "p1_splade",
    "p2_bm25",
    "p2_tfidf",
    "p3_bm25",
    "p3_tfidf",
    "baseline_qdrant_bm25",
    # Híbrido RRF (Cormack, Clarke & Buettcher 2009): combina un ranking
    # esparso (las 8 anteriores) con uno denso vía Qdrant. No tiene vectores
    # propios — compone los de las técnicas hijas. Por eso queda fuera de
    # `VECTOR_FILES` y los tests lo excluyen como técnica no-canónica.
    "hybrid_rrf",
)


# --- Baseline Qdrant BM25 -----------------------------------------------------
# Modelo y lengua del encoder fastembed con el que se vectorizó el corpus en
# Qdrant. Se usa en query-time para codificar la consulta con la misma
# función de hashing (MurmurHash3) y producir un vector compatible con los
# pesos pre-computados que viven en el campo `baseline_qdrant_bm25` del
# índice OpenSearch.
#
# `language="english"` no es un typo: aunque el corpus está en español, los
# vectores que el cliente Maqui.ai tiene en su instancia Qdrant fueron
# generados con `SparseTextEmbedding("Qdrant/bm25")` sin pasar `language`,
# y English es el default de fastembed. Se verificó empíricamente
# hasheando manualmente los chunks reales: cobertura 100% de hashes con
# Snowball English, 1% con Spanish. Cambiar a "spanish" rompe la baseline
# porque el stemmer español colapsa palabras (`impuesto`/`impuestos` -> `impuest`)
# que en el índice viven como hashes separados (sin colapsar).
BASELINE_QDRANT_BM25_MODEL = os.getenv("BASELINE_QDRANT_BM25_MODEL", "Qdrant/bm25")
BASELINE_QDRANT_BM25_LANGUAGE = os.getenv("BASELINE_QDRANT_BM25_LANGUAGE", "english")

# --- Variantes de scoring (presets) ------------------------------------------
# Ejes de evaluación adicionales sobre técnica × preprocesamiento.
#
# BM25_VARIANTS: cada entrada apunta a un campo hermano con la similarity
# correspondiente declarada en `schema.CHUNKS_MAPPING.settings.index.similarity`.
# El sufijo se concatena al nombre `content_pX` para resolver el campo a
# consultar. Default usa el campo original con la BM25 nativa de Lucene.
BM25_VARIANTS = {
    "default": {"label": "Default (k1=1.2, b=0.75)", "field_suffix": ""},
    "tuned_a": {"label": "Tuned A (k1=1.6, b=0.75)", "field_suffix": "_a"},
    "tuned_b": {"label": "Tuned B (k1=2.0, b=0.5)", "field_suffix": "_b"},
    "tuned_c": {"label": "Tuned C (k1=0.9, b=1.0)", "field_suffix": "_c"},
}

# RANK_FEATURE_VARIANTS: funciones de combinación que se aplican query-time
# sobre los pesos pre-computados de `tfidf_pX` y `splade_p1`. `function` y
# `params` se inyectan tal cual en cada cláusula `rank_feature` del bool/should.
RANK_FEATURE_VARIANTS = {
    "linear": {"label": "Linear (default)", "function": "linear", "params": {}},
    "saturation_p0_5": {
        "label": "Saturation (pivot=0.5)",
        "function": "saturation",
        "params": {"pivot": 0.5},
    },
    "saturation_p1": {
        "label": "Saturation (pivot=1.0)",
        "function": "saturation",
        "params": {"pivot": 1.0},
    },
    "saturation_p5": {
        "label": "Saturation (pivot=5.0)",
        "function": "saturation",
        "params": {"pivot": 5.0},
    },
    "saturation_p10": {
        "label": "Saturation (pivot=10.0)",
        "function": "saturation",
        "params": {"pivot": 10.0},
    },
}

DEFAULT_BM25_VARIANT = "default"
DEFAULT_RANK_FEATURE_VARIANT = "linear"


# --- Híbrido RRF --------------------------------------------------------------
# Reciprocal Rank Fusion (Cormack, Clarke & Buettcher 2009):
#     score_hybrid(d) = Σ_r 1 / (RRF_K + rank_r(d))
# La constante 60 del paper es la default de facto en Elasticsearch y Qdrant.
# Es el rank-floor que evita que el top-1 (rank=1) domine sobre todo el resto:
# con k=60 el incremento entre rank=1 y rank=2 (~0.000254) es comparable al
# que hay entre rank=5 y rank=20 — la fusión queda gradual, no winner-takes-all.
RRF_K = 60

# Cuántos candidatos pedir de cada lado antes de fusionar. RRF se beneficia de
# ver chunks que aparecen en una lista pero no en la otra, así que la pool
# de fusión debe ser bastante mayor que `size`. Cota inferior para que el
# top-k pedido tenga sentido aunque `size` sea chico (p.ej. size=5).
RRF_FETCH_MULTIPLIER = 5
RRF_FETCH_MIN = 50

# Ruta a los embeddings densos pre-computados de las queries del benchmark
# (Gemini `gemini-embedding-001`, 3072 dim, RETRIEVAL_QUERY). Lo produce
# `scripts/benchmark/embed_queries_gemini.py`. Se carga lazily la primera vez
# que se invoca `dense_qdrant.get_query_vector()`.
QUERIES_DENSE_PATH = os.getenv(
    "QUERIES_DENSE_PATH",
    "/app/scripts/benchmark/queries_dense/queries_dense.json",
)

# Carpeta donde viven los archivos qNNN_*.json del benchmark; se usa para
# poblar el dropdown del frontend cuando se elige hybrid_rrf. Es la única
# manera de saber qué queries tienen embedding denso pre-computado.
QUERIES_DIR = os.getenv("QUERIES_DIR", "/app/scripts/benchmark/queries")

# Catálogo de socios sparse para el RRF. El frontend lo usa como segundo
# dropdown cuando el usuario elige `hybrid_rrf`. El default es `p3_bm25`
# (BM25 con stemming Snowball), que es el baseline sparse estándar contra
# el que se compara hybrid en la literatura.
HYBRID_SPARSE_VARIANTS = {
    "p1_bm25": {"label": "P1 + BM25"},
    "p1_tfidf": {"label": "P1 + TF-IDF"},
    "p1_splade": {"label": "P1 + SPLADE"},
    "p2_bm25": {"label": "P2 + BM25"},
    "p2_tfidf": {"label": "P2 + TF-IDF"},
    "p3_bm25": {"label": "P3 + BM25"},
    "p3_tfidf": {"label": "P3 + TF-IDF"},
    "baseline_qdrant_bm25": {"label": "Baseline Qdrant BM25"},
}
DEFAULT_HYBRID_SPARSE = "p3_bm25"


# --- SPLADE encoder -----------------------------------------------------------
# Modelo HuggingFace usado en la fase de vectorización (ver
# Vectorizacion/sparse-benchmark/src/vectorizers.py). El backend lo carga al
# vuelo en query-time para encodear la consulta del usuario y obtener una
# representación esparsa comparable con los vectores indexados.
SPLADE_MODEL = os.getenv("SPLADE_MODEL", "naver/splade-cocondenser-ensembledistil")
SPLADE_MAX_LENGTH = int(os.getenv("SPLADE_MAX_LENGTH", "256"))
