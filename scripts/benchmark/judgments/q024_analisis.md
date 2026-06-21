# Análisis de retrieval — q024

**Query**: *"Reclamación judicial del monto de indemnización en expropiación de bien raíz"*
**Judgments**: 40 chunks evaluados
**Ganador top-10**: `p3_bm25` (mean_grade 2.800)

## Resultados

| Técnica | top-1 | P@1 | top-3 | P@3 | top-5 | P@5 | top-10 | P@10 | lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **p3_bm25** | 3.000 | 1.000 | **3.000** | **1.000** | 2.800 | 0.800 | **2.800** | **0.800** | 61 |
| p3_tfidf | 3.000 | 1.000 | **3.000** | **1.000** | **3.000** | **1.000** | 2.600 | 0.700 | 33 |
| p1_bm25 | 3.000 | 1.000 | 2.667 | 0.667 | 2.800 | 0.800 | 2.600 | 0.600 | 143 |
| p2_bm25 | 3.000 | 1.000 | 2.667 | 0.667 | 2.800 | 0.800 | 2.300 | 0.400 | 33 |
| p2_tfidf | 3.000 | 1.000 | 2.667 | 0.667 | 2.800 | 0.800 | 2.300 | 0.600 | 38 |
| p1_tfidf | 3.000 | 1.000 | 2.333 | 0.667 | 2.000 | 0.600 | 1.200 | 0.300 | 56 |
| p1_splade | 2.000 | 0.000 | 1.333 | 0.000 | 0.800 | 0.000 | 1.000 | 0.200 | 3134 |
| baseline_qdrant_bm25 | 0.000 | 0.000 | 0.333 | 0.000 | 0.200 | 0.000 | 0.400 | 0.000 | 1365 |

## Observaciones

Query "fácil" para retrievear: **seis técnicas empatan top-1=3.000 con P@1=1.000** (las tres BM25 y las tres TF-IDF). La cabeza del ranking es trivial — la query contiene términos discriminantes ("expropiación", "indemnización", "bien raíz") que aparecen co-ocurriendo en chunks muy específicos del corpus. La diferenciación entre técnicas se produce únicamente en profundidad.

**`p3_tfidf` consigue P@5=1.000** — los cinco primeros hits son todos altamente relevantes. Es el mejor caso de TF-IDF en todo el set y el único P@5 perfecto observado. Para un sistema que sirve top-5 al usuario, `p3_tfidf` sería estrictamente óptimo en esta query: precisión máxima en cabeza y latencia de 33ms.

`p3_bm25` gana top-10 (2.800) por sostener la calidad más allá del top-5, donde p3_tfidf cae a 2.600. Es la décima posición lo que define el ganador, no la cabeza. Ambos pertenecen al pipeline agresivo: p3 vuelve a destacar como en q023 — segunda query consecutiva donde el preprocesamiento más fuerte se impone. Patrón emergente en consultas con términos jurídicos morfológicamente cargados.

`p1_splade` rinde notablemente mal (top-1=2.000, top-10=1.000, P@5=0.000) — peor que cualquier TF-IDF excepto en top-10 vs `p1_tfidf`. En una query donde el matching léxico es directo, la expansión de SPLADE introduce ruido y desplaza chunks exactos por aproximados. 3134ms de latencia para entregar el peor desempeño esparso de la query.

El baseline denso toca fondo: **top-1=0.000** y top-10=0.400, peor que cualquier corrida en q021-q023. Para una query con vocabulario técnico muy específico ("expropiación de bien raíz"), los embeddings densos de 3072d no logran ni siquiera recuperar un primer hit aceptable — confirmación adicional del techo del método denso en este corpus.
