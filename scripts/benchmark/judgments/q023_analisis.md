# Análisis de retrieval — q023

**Query**: *"Recurso de apelación en juicio de arrendamiento de inmueble"*
**Judgments**: 54 chunks evaluados
**Ganador top-10**: `p3_bm25` (mean_grade 1.800)

## Resultados

| Técnica | top-1 | P@1 | top-3 | P@3 | top-5 | P@5 | top-10 | P@10 | lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **p3_bm25** | 2.000 | 0.000 | **1.667** | **0.333** | **2.000** | **0.400** | **1.800** | **0.400** | 67 |
| p1_bm25 | 2.000 | 0.000 | **1.667** | **0.333** | 1.400 | 0.200 | 1.500 | 0.100 | 116 |
| p1_splade | 0.000 | 0.000 | 1.000 | 0.000 | 0.800 | 0.000 | 1.300 | 0.100 | 3442 |
| p3_tfidf | **3.000** | **1.000** | **1.667** | **0.333** | 1.400 | 0.200 | 1.200 | 0.100 | 29 |
| p2_tfidf | 0.000 | 0.000 | 0.333 | 0.000 | 1.000 | 0.000 | 1.200 | 0.000 | 49 |
| p2_bm25 | 2.000 | 0.000 | 1.333 | 0.000 | 0.800 | 0.000 | 1.100 | 0.100 | 54 |
| baseline_qdrant_bm25 | 1.000 | 0.000 | 1.333 | 0.000 | 0.800 | 0.000 | 0.500 | 0.000 | 1444 |
| p1_tfidf | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.300 | 0.000 | 63 |

## Observaciones

Esta es la query **más difícil del set**. El máximo top-10 es 1.800 — por debajo del peor ganador de las otras queries del área. Ninguna técnica alcanza un mean_grade ≥ 2 en top-10, y `p3_bm25` gana con apenas 4 hits altamente relevantes en 10 posiciones (P@10=0.400). El corpus probablemente tiene pocos chunks que combinen los tres ejes de la consulta (recurso de apelación + arrendamiento + inmueble); las técnicas terminan recuperando fragmentos que cubren solo uno o dos.

**Comportamiento atípico en top-1**: `p3_tfidf` clava el primer hit con grade=3.000 (P@1=1.000) — único en todo el set y excepcional considerando que TF-IDF no había ganado top-1 en q021 ni q022. Pero el ranking colapsa después: top-3 cae a 1.667 y top-10 termina en 1.200. El primer hit es un golpe de suerte léxico, no una capacidad sostenida del modelo. Para chatbot top-1-único, `p3_tfidf` sería *la* opción; para top-3+ ya no.

**El pipeline 3 domina la query**: tanto `p3_bm25` (ganador top-10) como `p3_tfidf` (ganador top-1) están en el podio. Hipótesis: el preprocesamiento agresivo de p3 normaliza variantes morfológicas relevantes ("apelación"/"apelar", "arrendamiento"/"arrendar/arrendatario") que en p1 quedan como tokens distintos. Es el primer caso del set donde p3 muestra una ventaja clara sobre p1/p2.

`p1_tfidf` colapsa absoluto (top-10=0.300, P@k=0 en todo) — patrón ya observado en q022 pero acentuado acá. TF-IDF sin preprocesamiento intermedio o agresivo no resiste consultas con términos jurídicos morfológicamente flexionados.

SPLADE rinde **peor que casi todo**: top-1=0.000 y top-10=1.300, debajo incluso de `p2_tfidf`. Más 3442ms de latencia. Es el peor resultado de SPLADE en el set hasta acá; la expansión por sinónimos parece traer más ruido que señal cuando el corpus carece de buenos matches.

Qdrant denso vuelve al sótano (0.500 top-10), confirmando el patrón: cuando el corpus no tiene matches léxicos fuertes, los embeddings densos no salvan la situación — la "vecindad semántica" no es proxy útil de relevancia jurídica.
