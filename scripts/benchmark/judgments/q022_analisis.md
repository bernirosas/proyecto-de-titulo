# Análisis de retrieval — q022

**Query**: *"Reclamación de avalúo fiscal de bienes raíces ante el SII"*
**Judgments**: 54 chunks evaluados
**Ganador top-10**: `p1_bm25` (mean_grade 2.300, empatado con `p1_splade`)

## Resultados

| Técnica | top-1 | P@1 | top-3 | P@3 | top-5 | P@5 | top-10 | P@10 | lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **p1_bm25** | **3.000** | **1.000** | **2.333** | **0.333** | **2.400** | **0.400** | **2.300** | **0.300** | 47 |
| p1_splade | 2.000 | 0.000 | 2.333 | 0.333 | 2.200 | 0.200 | **2.300** | **0.300** | 2621 |
| p3_bm25 | 2.000 | 0.000 | 2.000 | 0.000 | 2.200 | 0.200 | 2.100 | 0.100 | 45 |
| p2_bm25 | 2.000 | 0.000 | 2.000 | 0.333 | 2.000 | 0.200 | 2.100 | 0.200 | 24 |
| baseline_qdrant_bm25 | 2.000 | 0.000 | 1.667 | 0.000 | 1.800 | 0.000 | 1.700 | 0.000 | 1369 |
| p1_tfidf | 2.000 | 0.000 | 2.000 | 0.000 | 2.000 | 0.000 | 1.700 | 0.000 | 23 |
| p2_tfidf | 2.000 | 0.000 | 1.667 | 0.000 | 1.600 | 0.000 | 1.700 | 0.100 | 18 |
| p3_tfidf | 2.000 | 0.000 | 1.333 | 0.000 | 1.600 | 0.000 | 1.700 | 0.000 | 19 |

## Observaciones

`p1_bm25` domina la query de extremo a extremo: único top-1 perfecto (3.000, P@1=1.000) y la mejor calidad en *todos* los cortes (top-3, top-5, top-10). Es la primera query del set donde una sola técnica gana de forma uniforme a lo largo de toda la profundidad del ranking. El preprocesamiento básico le alcanza — p2 y p3 no aportan nada y degradan el top-1.

`p1_splade` empata el top-10 (2.300) pero llega ahí por un camino opuesto: top-1 de 2.000 (P@1=0) que va remontando hacia abajo. Los hits altamente relevantes están repartidos en posiciones intermedias del ranking, no concentrados en la cabeza. Para una aplicación tipo chatbot legal donde top-1/top-3 son lo que importa, ese empate no es tal — `p1_bm25` es estrictamente mejor.

El costo del empate de SPLADE es **55x más latencia** (2621ms vs 47ms). Es el caso más limpio para descartar SPLADE en producción: misma calidad agregada al final del ranking, peor calidad en la cabeza, dos órdenes de magnitud más caro.

El baseline denso mejora respecto a q021 (1.700 vs 0.700 en top-10) y consigue top-1=2.000, pero P@k sigue en 0 en todos los cortes. Recupera chunks temáticamente cercanos al dominio tributario-inmobiliario pero falla en encontrar los hits altamente relevantes — sigue subordinado al léxico exacto que BM25 captura sin esfuerzo.

Las tres variantes de TF-IDF caen al fondo (top-10 ~1.700, P@k=0), por debajo incluso del baseline denso en top-10. Patrón consistente con q021: TF-IDF queda visiblemente atrás de BM25 en este corpus, sin importar el pipeline.
