# Reporte comparativo · sparse vs híbrido RRF

**Queries evaluadas**: 31
**Híbrido**: fusión RRF (k=60) del ranking denso (Gemini en Qdrant)
con cada uno de los 8 sparse partners.

Las métricas se reportan a varios k (1, 3, 5, 10) porque el comportamiento de la fusión RRF cambia con la profundidad: a top-1 el sparse suele dominar si la query es claramente léxica, y la fusión recupera terreno desde top-3 en adelante cuando entran chunks semánticos del lado denso.

## Head-to-head: `mean_grade` cross-k

Promedio cross-query de la relevancia (escala 0-3) en top-k. Δ = híbrido − sparse; positivo significa que la fusión mejora.

| Sparse partner | sparse @1 | híbrido @1 | Δ @1 | sparse @3 | híbrido @3 | Δ @3 | sparse @5 | híbrido @5 | Δ @5 | sparse @10 | híbrido @10 | Δ @10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_qdrant_bm25` | 2.097 | 2.161 | 0.064 | 2.011 | 2.075 | 0.064 | 1.923 | 2.006 | 0.083 | 1.703 | 1.946 | 0.243 |
| `p1_bm25` | 2.161 | 2.032 | -0.129 | 2.129 | 2.161 | 0.032 | 2.129 | 2.084 | -0.045 | 2.003 | 2.029 | 0.026 |
| `p1_splade` | 1.774 | 2.323 | 0.549 | 1.720 | 2.194 | 0.474 | 1.703 | 2.052 | 0.349 | 1.584 | 1.932 | 0.348 |
| `p1_tfidf` | 1.806 | 1.645 | -0.161 | 1.452 | 1.742 | 0.290 | 1.297 | 1.600 | 0.303 | 1.194 | 1.516 | 0.322 |
| `p2_bm25` | 2.290 | 2.226 | -0.064 | 2.161 | 2.280 | 0.119 | 2.065 | 2.226 | 0.161 | 1.961 | 2.100 | 0.139 |
| `p2_tfidf` | 1.903 | 2.097 | 0.194 | 1.796 | 2.086 | 0.290 | 1.735 | 2.013 | 0.278 | 1.603 | 1.873 | 0.270 |
| `p3_bm25` | 2.355 | 2.323 | -0.032 | 2.183 | 2.258 | 0.075 | 2.148 | 2.213 | 0.065 | 2.055 | 2.118 | 0.063 |
| `p3_tfidf` | 2.226 | 2.161 | -0.065 | 1.925 | 2.183 | 0.258 | 1.826 | 2.039 | 0.213 | 1.648 | 1.919 | 0.271 |

## Head-to-head: `P@k` cross-k (umbral estricto, grado=3)

Fracción de los primeros k chunks que el juez consideró *altamente relevantes* (grado 3). Métrica más estricta que mean_grade.

| Sparse partner | sparse @1 | híbrido @1 | Δ @1 | sparse @3 | híbrido @3 | Δ @3 | sparse @5 | híbrido @5 | Δ @5 | sparse @10 | híbrido @10 | Δ @10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_qdrant_bm25` | 0.419 | 0.452 | 0.033 | 0.419 | 0.419 | 0.000 | 0.335 | 0.381 | 0.046 | 0.226 | 0.324 | 0.098 |
| `p1_bm25` | 0.484 | 0.387 | -0.097 | 0.387 | 0.473 | 0.086 | 0.368 | 0.400 | 0.032 | 0.303 | 0.343 | 0.040 |
| `p1_splade` | 0.258 | 0.484 | 0.226 | 0.236 | 0.430 | 0.194 | 0.258 | 0.368 | 0.110 | 0.223 | 0.314 | 0.091 |
| `p1_tfidf` | 0.355 | 0.290 | -0.065 | 0.204 | 0.355 | 0.151 | 0.155 | 0.265 | 0.110 | 0.145 | 0.231 | 0.086 |
| `p2_bm25` | 0.516 | 0.484 | -0.032 | 0.387 | 0.484 | 0.097 | 0.348 | 0.452 | 0.104 | 0.303 | 0.354 | 0.051 |
| `p2_tfidf` | 0.419 | 0.452 | 0.033 | 0.355 | 0.441 | 0.086 | 0.303 | 0.374 | 0.071 | 0.239 | 0.319 | 0.080 |
| `p3_bm25` | 0.484 | 0.516 | 0.032 | 0.419 | 0.452 | 0.033 | 0.374 | 0.432 | 0.058 | 0.313 | 0.361 | 0.048 |
| `p3_tfidf` | 0.548 | 0.452 | -0.096 | 0.398 | 0.484 | 0.086 | 0.342 | 0.419 | 0.077 | 0.265 | 0.354 | 0.089 |

## Head-to-head: latencia (p50, p95)

p50 refleja el steady-state (no contaminado por el cold-start de la primera query del proceso warm). p95 da una idea del peor caso razonable. El híbrido siempre paga el costo de OpenSearch + Qdrant + fusión, así que su latencia es necesariamente mayor.

| Sparse partner | sparse p50 (ms) | híbrido p50 (ms) | Δ p50 | sparse p95 (ms) | híbrido p95 (ms) | Δ p95 |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_qdrant_bm25` | 11.6 | 45.2 | 33.6 | 22.5 | 73.2 | 50.7 |
| `p1_bm25` | 13.0 | 61.5 | 48.5 | 18.5 | 190.4 | 171.9 |
| `p1_splade` | 103.9 | 150.5 | 46.6 | 165.9 | 237.5 | 71.6 |
| `p1_tfidf` | 13.1 | 54.2 | 41.1 | 19.8 | 88.4 | 68.6 |
| `p2_bm25` | 11.4 | 175.8 | 164.4 | 23.6 | 203.9 | 180.3 |
| `p2_tfidf` | 10.7 | 163.2 | 152.5 | 22.5 | 197.3 | 174.8 |
| `p3_bm25` | 8.9 | 67.0 | 58.1 | 15.9 | 110.2 | 94.3 |
| `p3_tfidf` | 8.0 | 66.1 | 58.1 | 13.5 | 88.8 | 75.3 |

## Ranking global (sparse + híbrido mezclados)

Las 16 técnicas ordenadas por `mean_grade@10` cross-query. Permite ver de un vistazo qué porcentaje del top-N son híbridos.

| Rank | Técnica | Familia | mean_grade@10 | P@5 | lat p50 (ms) |
|---:|---|---|---:|---:|---:|
| 1 | `rrf_p3_bm25` | híbrido | 2.118 | 0.432 | 67.0 |
| 2 | `rrf_p2_bm25` | híbrido | 2.100 | 0.452 | 175.8 |
| 3 | `p3_bm25` | sparse | 2.055 | 0.374 | 8.9 |
| 4 | `rrf_p1_bm25` | híbrido | 2.029 | 0.400 | 61.5 |
| 5 | `p1_bm25` | sparse | 2.003 | 0.368 | 13.0 |
| 6 | `p2_bm25` | sparse | 1.961 | 0.348 | 11.4 |
| 7 | `rrf_baseline_qdrant_bm25` | híbrido | 1.946 | 0.381 | 45.2 |
| 8 | `rrf_p1_splade` | híbrido | 1.932 | 0.368 | 150.5 |
| 9 | `rrf_p3_tfidf` | híbrido | 1.919 | 0.419 | 66.1 |
| 10 | `rrf_p2_tfidf` | híbrido | 1.873 | 0.374 | 163.2 |
| 11 | `baseline_qdrant_bm25` | sparse | 1.703 | 0.335 | 11.6 |
| 12 | `p3_tfidf` | sparse | 1.648 | 0.342 | 8.0 |
| 13 | `p2_tfidf` | sparse | 1.603 | 0.303 | 10.7 |
| 14 | `p1_splade` | sparse | 1.584 | 0.258 | 103.9 |
| 15 | `rrf_p1_tfidf` | híbrido | 1.516 | 0.265 | 54.2 |
| 16 | `p1_tfidf` | sparse | 1.194 | 0.155 | 13.1 |

## Cuándo gana el híbrido

Por query y por par sparse↔híbrido, contamos 1 victoria si `rrf_X` tiene mejor `mean_grade@10` que `X` en esa query. El score por query es la tasa de victorias del híbrido (0-1) sobre los pares con ambos lados disponibles.

| Query | Tasa victorias híbrido | Victorias / Total pares |
|---|---:|---:|
| `q004` | 1.00 | 8 / 8 |
| `q009` | 1.00 | 8 / 8 |
| `q012` | 1.00 | 8 / 8 |
| `q015` | 1.00 | 8 / 8 |
| `q017` | 1.00 | 8 / 8 |
| `q019` | 1.00 | 8 / 8 |
| `q020` | 1.00 | 8 / 8 |
| `q010` | 0.88 | 7 / 8 |
| `q013` | 0.88 | 7 / 8 |
| `q018` | 0.88 | 7 / 8 |
| `q023` | 0.88 | 7 / 8 |
| `q028` | 0.88 | 7 / 8 |
| `q000` | 0.75 | 6 / 8 |
| `q003` | 0.75 | 6 / 8 |
| `q006` | 0.75 | 6 / 8 |
| `q011` | 0.75 | 6 / 8 |
| `q021` | 0.75 | 6 / 8 |
| `q022` | 0.75 | 6 / 8 |
| `q008` | 0.62 | 5 / 8 |
| `q016` | 0.62 | 5 / 8 |
| `q024` | 0.62 | 5 / 8 |
| `q025` | 0.62 | 5 / 8 |
| `q027` | 0.62 | 5 / 8 |
| `q002` | 0.50 | 4 / 8 |
| `q007` | 0.50 | 4 / 8 |
| `q030` | 0.50 | 4 / 8 |
| `q005` | 0.38 | 3 / 8 |
| `q029` | 0.38 | 3 / 8 |
| `q001` | 0.25 | 2 / 8 |
| `q014` | 0.12 | 1 / 8 |
| `q026` | 0.12 | 1 / 8 |

**Tasa global de victorias del híbrido**: 70.16%

