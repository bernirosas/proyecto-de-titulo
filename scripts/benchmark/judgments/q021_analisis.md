# Análisis de retrieval — q021

**Query**: *"Recurso de protección por afectación al derecho de propiedad sobre inmueble"*
**Judgments**: 47 chunks evaluados
**Ganador top-10**: `p2_bm25` (mean_grade 2.300)

## Resultados

| Técnica | top-1 | P@1 | top-3 | P@3 | top-5 | P@5 | top-10 | P@10 | lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **p2_bm25** | **3.000** | **1.000** | **2.333** | **0.333** | 2.200 | 0.200 | **2.300** | **0.300** | 51 |
| p1_bm25 | 3.000 | 1.000 | 2.333 | 0.333 | **2.400** | **0.400** | 2.200 | 0.200 | 93 |
| p3_bm25 | 2.000 | 0.000 | 2.000 | 0.000 | 2.000 | 0.000 | 2.100 | 0.100 | 76 |
| p1_splade | 3.000 | 1.000 | 1.667 | 0.333 | 1.800 | 0.200 | 1.900 | 0.300 | 3724 |
| p2_tfidf | 2.000 | 0.000 | 2.000 | 0.333 | 2.200 | 0.400 | 1.900 | 0.200 | 45 |
| p3_tfidf | 2.000 | 0.000 | 2.000 | 0.333 | 1.400 | 0.200 | 1.500 | 0.200 | 30 |
| p1_tfidf | 2.000 | 0.000 | 1.333 | 0.000 | 0.800 | 0.000 | 0.500 | 0.000 | 40 |
| baseline_qdrant_bm25 | 0.000 | 0.000 | 1.000 | 0.000 | 0.800 | 0.000 | 0.700 | 0.000 | 1447 |

## Observaciones

El ranking top-10 lo lidera `p2_bm25` por un margen muy ajustado sobre `p1_bm25` (2.300 vs 2.200). Las dos variantes son indistinguibles en top-1 y top-3 — el desempate aparece recién en top-5/10, donde el preprocesamiento intermedio de p2 mantiene marginalmente más chunks útiles en la cola. La diferencia es chica como para atribuirla con confianza al pipeline; lo robusto del hallazgo es que **BM25 sobre cualquier pipeline supera al resto de las familias**, en línea con las otras queries del set.

Tres técnicas empatan top-1 perfecto (`p1_bm25`, `p1_splade`, `p2_bm25` con grade=3.000 y P@1=1.000): la cabeza del ranking es trivial para esta query. La diferenciación aparece en profundidad — `p1_splade` cae a 1.900 en top-10 mientras los BM25 sostienen ~2.2-2.3. SPLADE recupera bien el primer hit pero contamina rápido el ranking con sinónimos espurios.

`p1_tfidf` colapsa: 0.500 en top-10 y P@k=0 en todos los k. Es la peor técnica esparsa del corte, peor incluso que `p2_tfidf` y `p3_tfidf` con el mismo modelo subyacente. Sugiere que TF-IDF sin preprocesamiento intermedio es especialmente frágil a la dispersión léxica de la query — "recurso de protección", "derecho de propiedad" e "inmueble" son términos de alta frecuencia documental en el corpus.

El baseline denso (`baseline_qdrant_bm25`, embeddings 3072d) es catastrófico: top-1=0.000, top-10=0.700, P@k=0 en todos los puntos. La similitud coseno sobre el espacio de embeddings devuelve chunks tematicamente vecinos pero jurídicamente irrelevantes — confirmación fuerte de que el dominio legal chileno premia coincidencia léxica sobre cercanía semántica generalista.

SPLADE es ~70x más lento que `p2_bm25` (3724ms vs 51ms) para entregar peor calidad en top-10. El trade-off latencia/calidad es claramente desfavorable y se repite en las otras queries del set.
