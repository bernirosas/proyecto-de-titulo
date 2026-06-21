"""Mapping del índice chunks_maqui (versión agnóstica al preprocesamiento).

Cambio clave respecto de versiones anteriores: OpenSearch ya NO aplica un
analizador propio (antes era spanish_legal con hunspell). El preprocesamiento
se hace upstream en `Vectorizacion/sparse-benchmark/src/preprocessors.py` y
los tokens preprocesados se ingresan tal cual.

Campos por técnica:
  - content_p{1,2,3}  : texto con los tokens P1/P2/P3 ya joinados con espacio.
                       analyzer = whitespace_lower, que NO toca los tokens
                       (solo los separa por espacio y baja a minúscula). El
                       BM25 nativo de Lucene puntúa sobre estos campos.
  - tfidf_p{1,2,3}    : rank_features con los pesos TF-IDF pre-computados
                       en la fase de vectorización. Una entrada por token
                       distinto.

Reservado pero no poblado en esta versión: SPLADE y BGEM3 (Fase 2).

El campo `content` original se conserva en texto crudo para mostrar al
usuario en los hits, sin participar del scoring.
"""

CHUNKS_MAPPING = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    # Whitespace + lowercase. Pensado para tokens que ya
                    # vienen preprocesados desde fuera. No aplica stemming,
                    # lematización, stopwords, ni normalización Unicode.
                    "whitespace_lower": {
                        "type": "custom",
                        "tokenizer": "whitespace",
                        "filter": ["lowercase"],
                    },
                },
            },
            # Similarities BM25 alternativas. Cada entrada habilita un campo
            # hermano `content_pX_{a,b,c}` con esos parámetros, lo que permite
            # comparar configuraciones de scoring contra el default sin
            # reindexar. Mantener sincronizado con `config.BM25_VARIANTS`.
            "similarity": {
                "bm25_tuned_a": {"type": "BM25", "k1": 1.6, "b": 0.75},
                "bm25_tuned_b": {"type": "BM25", "k1": 2.0, "b": 0.5},
                "bm25_tuned_c": {"type": "BM25", "k1": 0.9, "b": 1.0},
            },
        }
    },
    "mappings": {
        "properties": {
            # --- Identidad ---
            "chunk_uuid": {"type": "keyword"},
            "chunk_id": {"type": "integer"},
            "document_id": {"type": "keyword"},
            # --- Identidad externa del documento ---
            "external_id": {"type": "long"},
            "filename": {"type": "keyword"},
            # --- Metadatos descriptivos del documento (denormalizados) ---
            "name": {"type": "text"},
            "source": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            # --- Atributos específicos de subtipo (nullable) ---
            "rol_number": {"type": "keyword"},  # solo jurisprudencia
            "bcn_id_norm": {"type": "long"},  # solo ley
            "instance_name": {"type": "keyword"},  # solo jurisprudencia
            "court_specific_name": {"type": "keyword"},  # solo jurisprudencia
            # --- Temporalidad ---
            "date": {"type": "date"},
            "publication_date": {"type": "date"},
            # --- Referencia pública ---
            "url": {"type": "keyword", "index": False},
            # --- Contenido crudo (solo para mostrar, no se puntúa contra esto) ---
            "content": {"type": "text"},
            "char_length": {"type": "integer"},
            # --- Tokens preprocesados, joinados con espacio. BM25 puntúa acá. ---
            # Cada `content_pX` se replica vía `copy_to` a 3 campos hermanos
            # con BM25 tuneado (variantes a/b/c). Esto permite seleccionar la
            # función de scoring desde la query sin reindexar. Los campos
            # hermanos comparten el mismo texto pero usan distinta similarity
            # de Lucene.
            "content_p1": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "BM25",
                "copy_to": ["content_p1_a", "content_p1_b", "content_p1_c"],
            },
            "content_p1_a": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_a",
            },
            "content_p1_b": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_b",
            },
            "content_p1_c": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_c",
            },
            "content_p2": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "BM25",
                "copy_to": ["content_p2_a", "content_p2_b", "content_p2_c"],
            },
            "content_p2_a": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_a",
            },
            "content_p2_b": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_b",
            },
            "content_p2_c": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_c",
            },
            "content_p3": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "BM25",
                "copy_to": ["content_p3_a", "content_p3_b", "content_p3_c"],
            },
            "content_p3_a": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_a",
            },
            "content_p3_b": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_b",
            },
            "content_p3_c": {
                "type": "text",
                "analyzer": "whitespace_lower",
                "similarity": "bm25_tuned_c",
            },
            # --- Vectores TF-IDF pre-computados (uno por preprocesamiento) ---
            "tfidf_p1": {"type": "rank_features"},
            "tfidf_p2": {"type": "rank_features"},
            "tfidf_p3": {"type": "rank_features"},
            # --- Vectores SPLADE pre-computados (modelo
            # naver/splade-cocondenser-ensembledistil sobre el texto P1
            # limpio). Las claves son tokens WordPiece BERT (~30k vocab),
            # mucho menos densos que TF-IDF (~290 tokens activos por chunk
            # vs ~250 para TF-IDF). ---
            "splade_p1": {"type": "rank_features"},
            # --- Baseline Qdrant BM25 (fastembed `Qdrant/bm25` con stemmer
            # Snowball — English por default de la librería, que es lo que
            # el cliente Maqui.ai usa en producción; verificado empíricamente
            # contra el snapshot extraído de su Qdrant). Las claves son
            # MurmurHash3 enteros como string (p. ej. "823349694"). Los
            # vectores se extrajeron tal cual de la instancia Qdrant del
            # cliente para comparar contra nuestras implementaciones BM25
            # (p1/p2/p3 + Lucene native) y revelar cualquier diferencia
            # atribuible a la pipeline de upstream. ---
            "baseline_qdrant_bm25": {"type": "rank_features"},
        }
    },
}
