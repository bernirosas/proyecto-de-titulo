# Reporte híbrido (RRF) del benchmark

_Los 8 combos `rrf_<sparse>`: fusión Reciprocal Rank Fusion (k=60) del ranking denso Gemini con cada sparse partner._

**Queries evaluadas**: 31 (7 temas representados)
**Métricas reportadas**: mean, mediana (p50), percentil 95

Las estadísticas son agregaciones cross-query: cada técnica recibe un valor por query (un `mean_grade@10`, un `P@5`, una latencia) y de esos valores se sacan mean / p50 / p95. Esto refleja cómo se comporta cada técnica en distintas consultas del dominio, no varianza intra-query.

## Resumen global

**Técnica ganadora**: `rrf_p3_bm25` (mean del `mean_grade@10` cross-query = 2.118)

### Calidad: `mean_grade @ top-10`

Promedio de la relevancia (escala 0-3) sobre los 10 primeros chunks.

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_bm25` | 2.118 | 2.200 | 2.700 | 31 |
| `rrf_p2_bm25` | 2.100 | 2.200 | 2.800 | 31 |
| `rrf_p1_bm25` | 2.029 | 2.200 | 2.700 | 31 |
| `rrf_baseline_qdrant_bm25` | 1.946 | 2.100 | 2.800 | 31 |
| `rrf_p1_splade` | 1.932 | 2.100 | 2.800 | 31 |
| `rrf_p3_tfidf` | 1.919 | 2.111 | 2.750 | 31 |
| `rrf_p2_tfidf` | 1.873 | 2 | 2.800 | 31 |
| `rrf_p1_tfidf` | 1.516 | 1.667 | 2.500 | 31 |

### Precisión: `P@5` (umbral estricto, grado = 3)

Fracción de los 5 primeros chunks que el juez consideró *altamente relevantes* (grado 3).

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_bm25` | 0.452 | 0.400 | 1.000 | 31 |
| `rrf_p3_bm25` | 0.432 | 0.400 | 0.800 | 31 |
| `rrf_p3_tfidf` | 0.419 | 0.400 | 0.800 | 31 |
| `rrf_p1_bm25` | 0.400 | 0.400 | 0.800 | 31 |
| `rrf_baseline_qdrant_bm25` | 0.381 | 0.400 | 0.800 | 31 |
| `rrf_p2_tfidf` | 0.374 | 0.400 | 0.800 | 31 |
| `rrf_p1_splade` | 0.368 | 0.400 | 0.800 | 31 |
| `rrf_p1_tfidf` | 0.265 | 0.000 | 0.800 | 31 |

### Latencia end-to-end (ms)

Tiempo de respuesta de cada técnica (preproc/encoder + I/O a OpenSearch). NO incluye highlights ni post-procesamiento.

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 45.2 | 73.2 | 55.5 | 31 |
| `rrf_p1_tfidf` | 54.2 | 88.4 | 64.0 | 31 |
| `rrf_p1_bm25` | 61.5 | 190.4 | 81.3 | 31 |
| `rrf_p3_tfidf` | 66.1 | 88.8 | 74.1 | 31 |
| `rrf_p3_bm25` | 67.0 | 110.2 | 69.7 | 31 |
| `rrf_p1_splade` | 150.5 | 237.5 | 168.5 | 31 |
| `rrf_p2_tfidf` | 163.2 | 197.3 | 157.0 | 31 |
| `rrf_p2_bm25` | 175.8 | 203.9 | 166.3 | 31 |

## Desglose por tema

Para cada tema se reportan las mismas tres métricas. Si una técnica destaca en un tema pero no en otros, ahí está la pista experimental.

### Arrendamientos

**Queries**: `q001`, `q002`, `q003`, `q004`, `q005`  (N = 5)
**Ganadora del tema**: `rrf_p3_bm25` (mean `mean_grade@10` = 1.252)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_bm25` | 1.252 | 1.429 | 2 | 5 |
| `rrf_p2_bm25` | 1.157 | 1.143 | 2 | 5 |
| `rrf_p1_splade` | 1.043 | 1 | 2.100 | 5 |
| `rrf_p1_bm25` | 0.969 | 1.100 | 2 | 5 |
| `rrf_p3_tfidf` | 0.839 | 0.500 | 2 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.665 | 0.444 | 2 | 5 |
| `rrf_p2_tfidf` | 0.657 | 0.429 | 2 | 5 |
| `rrf_p1_tfidf` | 0.652 | 0.429 | 2 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_bm25` | 0.040 | 0.000 | 0.200 | 5 |
| `rrf_p3_bm25` | 0.040 | 0.000 | 0.200 | 5 |
| `rrf_p3_tfidf` | 0.040 | 0.000 | 0.200 | 5 |
| `rrf_p1_bm25` | 0.000 | 0.000 | 0.000 | 5 |
| `rrf_p1_tfidf` | 0.000 | 0.000 | 0.000 | 5 |
| `rrf_p1_splade` | 0.000 | 0.000 | 0.000 | 5 |
| `rrf_p2_tfidf` | 0.000 | 0.000 | 0.000 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.000 | 0.000 | 0.000 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 45.2 | 57.4 | 46.9 | 5 |
| `rrf_p1_tfidf` | 61.5 | 174.7 | 80.0 | 5 |
| `rrf_p3_bm25` | 67.0 | 74.0 | 65.5 | 5 |
| `rrf_p3_tfidf` | 72.2 | 82.3 | 70.8 | 5 |
| `rrf_p1_bm25` | 83.9 | 218.9 | 107.7 | 5 |
| `rrf_p1_splade` | 143.6 | 237.5 | 151.5 | 5 |
| `rrf_p2_tfidf` | 144.0 | 194.3 | 152.9 | 5 |
| `rrf_p2_bm25` | 175.8 | 192.7 | 168.1 | 5 |

### Compraventa

**Queries**: `q006`, `q007`, `q008`, `q009`, `q010`  (N = 5)
**Ganadora del tema**: `rrf_p3_tfidf` (mean `mean_grade@10` = 2.403)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_tfidf` | 2.403 | 2.600 | 2.800 | 5 |
| `rrf_p1_bm25` | 2.353 | 2.400 | 2.900 | 5 |
| `rrf_baseline_qdrant_bm25` | 2.353 | 2.500 | 2.900 | 5 |
| `rrf_p3_bm25` | 2.340 | 2.400 | 2.900 | 5 |
| `rrf_p2_bm25` | 2.334 | 2.400 | 2.900 | 5 |
| `rrf_p2_tfidf` | 2.281 | 2.500 | 2.900 | 5 |
| `rrf_p1_splade` | 2.189 | 2.300 | 2.500 | 5 |
| `rrf_p1_tfidf` | 1.607 | 1.600 | 2.900 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_tfidf` | 0.600 | 0.800 | 1.000 | 5 |
| `rrf_p3_bm25` | 0.560 | 0.600 | 0.800 | 5 |
| `rrf_p2_tfidf` | 0.520 | 0.600 | 0.800 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.520 | 0.600 | 0.800 | 5 |
| `rrf_p1_bm25` | 0.480 | 0.400 | 0.800 | 5 |
| `rrf_p1_splade` | 0.480 | 0.600 | 0.800 | 5 |
| `rrf_p2_bm25` | 0.480 | 0.600 | 0.800 | 5 |
| `rrf_p1_tfidf` | 0.320 | 0.200 | 0.800 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 41.0 | 73.2 | 47.5 | 5 |
| `rrf_p1_tfidf` | 58.0 | 66.8 | 56.8 | 5 |
| `rrf_p1_bm25` | 59.0 | 76.3 | 59.5 | 5 |
| `rrf_p3_tfidf` | 59.6 | 70.4 | 58.2 | 5 |
| `rrf_p3_bm25` | 65.3 | 70.8 | 61.0 | 5 |
| `rrf_p1_splade` | 150.5 | 227.1 | 163.5 | 5 |
| `rrf_p2_bm25` | 155.5 | 190.9 | 146.2 | 5 |
| `rrf_p2_tfidf` | 163.2 | 195.5 | 150.2 | 5 |

### Copropiedad / Propiedad horizontal

**Queries**: `q011`, `q012`, `q013`, `q014`, `q015`  (N = 5)
**Ganadora del tema**: `rrf_p3_tfidf` (mean `mean_grade@10` = 2.325)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_tfidf` | 2.325 | 2.125 | 2.900 | 5 |
| `rrf_p1_bm25` | 2.300 | 2.200 | 2.800 | 5 |
| `rrf_p2_bm25` | 2.300 | 2.300 | 2.700 | 5 |
| `rrf_p3_bm25` | 2.300 | 2.300 | 2.700 | 5 |
| `rrf_p2_tfidf` | 2.227 | 2.111 | 2.900 | 5 |
| `rrf_baseline_qdrant_bm25` | 2.205 | 2.125 | 2.700 | 5 |
| `rrf_p1_splade` | 2.105 | 2 | 2.600 | 5 |
| `rrf_p1_tfidf` | 1.890 | 1.714 | 2.400 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_bm25` | 0.560 | 0.600 | 1.000 | 5 |
| `rrf_p1_bm25` | 0.520 | 0.600 | 1.000 | 5 |
| `rrf_p3_bm25` | 0.480 | 0.600 | 0.800 | 5 |
| `rrf_p3_tfidf` | 0.440 | 0.200 | 1.000 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.440 | 0.400 | 1.000 | 5 |
| `rrf_p1_tfidf` | 0.320 | 0.400 | 0.800 | 5 |
| `rrf_p1_splade` | 0.320 | 0.200 | 0.600 | 5 |
| `rrf_p2_tfidf` | 0.320 | 0.200 | 0.800 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 47.5 | 64.6 | 46.5 | 5 |
| `rrf_p1_bm25` | 55.9 | 74.6 | 59.4 | 5 |
| `rrf_p1_tfidf` | 56.6 | 63.1 | 55.8 | 5 |
| `rrf_p3_bm25` | 64.6 | 115.9 | 74.8 | 5 |
| `rrf_p3_tfidf` | 68.4 | 70.9 | 65.8 | 5 |
| `rrf_p1_splade` | 161.9 | 226.1 | 175.7 | 5 |
| `rrf_p2_tfidf` | 171.8 | 190.2 | 173.7 | 5 |
| `rrf_p2_bm25` | 188.6 | 203.4 | 186.7 | 5 |

### Tributación inmobiliaria

**Queries**: `q016`, `q017`, `q018`, `q019`, `q020`  (N = 5)
**Ganadora del tema**: `rrf_p2_tfidf` (mean `mean_grade@10` = 2.605)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_tfidf` | 2.605 | 2.600 | 2.800 | 5 |
| `rrf_p3_tfidf` | 2.590 | 2.700 | 2.750 | 5 |
| `rrf_p1_bm25` | 2.535 | 2.600 | 2.700 | 5 |
| `rrf_p1_splade` | 2.500 | 2.600 | 2.800 | 5 |
| `rrf_p1_tfidf` | 2.487 | 2.500 | 2.700 | 5 |
| `rrf_p2_bm25` | 2.460 | 2.600 | 2.900 | 5 |
| `rrf_p3_bm25` | 2.460 | 2.600 | 2.800 | 5 |
| `rrf_baseline_qdrant_bm25` | 2.460 | 2.500 | 2.800 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_tfidf` | 0.800 | 0.800 | 1.000 | 5 |
| `rrf_p2_bm25` | 0.720 | 0.800 | 1.000 | 5 |
| `rrf_p1_bm25` | 0.680 | 0.600 | 1.000 | 5 |
| `rrf_p1_splade` | 0.680 | 0.800 | 1.000 | 5 |
| `rrf_p3_tfidf` | 0.680 | 0.600 | 0.800 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.680 | 0.800 | 1.000 | 5 |
| `rrf_p3_bm25` | 0.640 | 0.600 | 1.000 | 5 |
| `rrf_p1_tfidf` | 0.600 | 0.600 | 0.800 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 47.9 | 115.2 | 58.6 | 5 |
| `rrf_p1_tfidf` | 52.9 | 79.5 | 56.9 | 5 |
| `rrf_p1_bm25` | 68.8 | 87.9 | 69.7 | 5 |
| `rrf_p3_bm25` | 73.6 | 110.2 | 76.4 | 5 |
| `rrf_p3_tfidf` | 86.9 | 272.2 | 119.5 | 5 |
| `rrf_p1_splade` | 136.2 | 238.2 | 167.5 | 5 |
| `rrf_p2_tfidf` | 191.2 | 250.9 | 193.0 | 5 |
| `rrf_p2_bm25` | 203.9 | 302.2 | 216.2 | 5 |

### Recursos sobre bienes raíces

**Queries**: `q021`, `q022`, `q023`, `q024`, `q025`  (N = 5)
**Ganadora del tema**: `rrf_baseline_qdrant_bm25` (mean `mean_grade@10` = 2.380)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 2.380 | 2.375 | 2.800 | 5 |
| `rrf_p2_bm25` | 2.339 | 2.250 | 2.800 | 5 |
| `rrf_p3_bm25` | 2.282 | 2.200 | 2.600 | 5 |
| `rrf_p1_splade` | 2.160 | 2.250 | 2.800 | 5 |
| `rrf_p1_bm25` | 2.150 | 2.100 | 2.400 | 5 |
| `rrf_p3_tfidf` | 2.149 | 2.111 | 2.556 | 5 |
| `rrf_p2_tfidf` | 2.037 | 2.125 | 2.625 | 5 |
| `rrf_p1_tfidf` | 1.269 | 1.200 | 2.143 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_bm25` | 0.560 | 0.600 | 1.000 | 5 |
| `rrf_p1_splade` | 0.520 | 0.600 | 0.800 | 5 |
| `rrf_p3_bm25` | 0.480 | 0.600 | 0.800 | 5 |
| `rrf_p3_tfidf` | 0.480 | 0.400 | 0.800 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.480 | 0.600 | 0.800 | 5 |
| `rrf_p1_bm25` | 0.440 | 0.400 | 0.800 | 5 |
| `rrf_p2_tfidf` | 0.360 | 0.400 | 0.800 | 5 |
| `rrf_p1_tfidf` | 0.200 | 0.000 | 0.800 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 49.3 | 54.1 | 47.7 | 5 |
| `rrf_p1_tfidf` | 54.2 | 172.4 | 83.9 | 5 |
| `rrf_p1_bm25` | 63.9 | 190.4 | 90.2 | 5 |
| `rrf_p3_tfidf` | 64.6 | 81.8 | 66.3 | 5 |
| `rrf_p3_bm25` | 68.9 | 107.4 | 75.6 | 5 |
| `rrf_p2_tfidf` | 140.9 | 182.6 | 135.3 | 5 |
| `rrf_p1_splade` | 166.2 | 359.2 | 202.1 | 5 |
| `rrf_p2_bm25` | 177.8 | 200.1 | 159.5 | 5 |

### Jurisprudencia de inmuebles

**Queries**: `q026`, `q027`, `q028`, `q029`, `q030`  (N = 5)
**Ganadora del tema**: `rrf_p3_bm25` (mean `mean_grade@10` = 1.999)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p3_bm25` | 1.999 | 2 | 2.300 | 5 |
| `rrf_p2_bm25` | 1.952 | 1.800 | 2.300 | 5 |
| `rrf_p1_bm25` | 1.792 | 1.875 | 2.333 | 5 |
| `rrf_baseline_qdrant_bm25` | 1.503 | 1.500 | 2.167 | 5 |
| `rrf_p1_splade` | 1.459 | 1.400 | 2.200 | 5 |
| `rrf_p2_tfidf` | 1.303 | 1.444 | 1.600 | 5 |
| `rrf_p3_tfidf` | 1.091 | 1.300 | 1.556 | 5 |
| `rrf_p1_tfidf` | 1.015 | 1 | 1.444 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p2_bm25` | 0.320 | 0.200 | 0.800 | 5 |
| `rrf_p3_bm25` | 0.320 | 0.200 | 0.800 | 5 |
| `rrf_p1_bm25` | 0.240 | 0.200 | 0.600 | 5 |
| `rrf_p3_tfidf` | 0.200 | 0.200 | 0.400 | 5 |
| `rrf_p2_tfidf` | 0.160 | 0.200 | 0.400 | 5 |
| `rrf_p1_splade` | 0.120 | 0.000 | 0.400 | 5 |
| `rrf_baseline_qdrant_bm25` | 0.080 | 0.000 | 0.200 | 5 |
| `rrf_p1_tfidf` | 0.040 | 0.000 | 0.200 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_baseline_qdrant_bm25` | 43.2 | 69.6 | 48.7 | 5 |
| `rrf_p1_tfidf` | 47.6 | 60.4 | 49.3 | 5 |
| `rrf_p1_bm25` | 51.3 | 74.2 | 54.2 | 5 |
| `rrf_p3_bm25` | 53.0 | 120.2 | 65.3 | 5 |
| `rrf_p3_tfidf` | 56.9 | 65.6 | 57.6 | 5 |
| `rrf_p2_tfidf` | 119.4 | 178.8 | 128.6 | 5 |
| `rrf_p2_bm25` | 121.1 | 171.2 | 115.1 | 5 |
| `rrf_p1_splade` | 154.7 | 184.7 | 151.5 | 5 |

### Sanity check (seed)

**Queries**: `q000`  (N = 1)
**Ganadora del tema**: `rrf_p1_splade` (mean `mean_grade@10` = 2.600)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p1_splade` | 2.600 | 2.600 | 2.600 | 1 |
| `rrf_p2_tfidf` | 2.500 | 2.500 | 2.500 | 1 |
| `rrf_p3_bm25` | 2.500 | 2.500 | 2.500 | 1 |
| `rrf_p3_tfidf` | 2.500 | 2.500 | 2.500 | 1 |
| `rrf_baseline_qdrant_bm25` | 2.500 | 2.500 | 2.500 | 1 |
| `rrf_p1_bm25` | 2.400 | 2.400 | 2.400 | 1 |
| `rrf_p1_tfidf` | 2.400 | 2.400 | 2.400 | 1 |
| `rrf_p2_bm25` | 2.400 | 2.400 | 2.400 | 1 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `rrf_p1_tfidf` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_p1_splade` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_p2_tfidf` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_p3_bm25` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_p3_tfidf` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_baseline_qdrant_bm25` | 0.800 | 0.800 | 0.800 | 1 |
| `rrf_p1_bm25` | 0.600 | 0.600 | 0.600 | 1 |
| `rrf_p2_bm25` | 0.600 | 0.600 | 0.600 | 1 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `rrf_p3_bm25` | 68.8 | 68.8 | 68.8 | 1 |
| `rrf_p1_tfidf` | 71.0 | 71.0 | 71.0 | 1 |
| `rrf_p3_tfidf` | 104.6 | 104.6 | 104.6 | 1 |
| `rrf_p1_splade` | 164.6 | 164.6 | 164.6 | 1 |
| `rrf_p2_bm25` | 197.0 | 197.0 | 197.0 | 1 |
| `rrf_p2_tfidf` | 197.3 | 197.3 | 197.3 | 1 |
| `rrf_baseline_qdrant_bm25` | 242.5 | 242.5 | 242.5 | 1 |
| `rrf_p1_bm25` | 318.2 | 318.2 | 318.2 | 1 |

## Ranking final (calidad vs costo)

Tabla resumen que ordena las técnicas por calidad y muestra el costo asociado. Útil para argumentar trade-offs en la sección de discusión.

| Rank | Técnica | mean_grade@10 (mean) | P@5 (mean) | lat ms (p50) |
|---:|---|---:|---:|---:|
| 1 | `rrf_p3_bm25` | 2.118 | 0.432 | 67.0 |
| 2 | `rrf_p2_bm25` | 2.100 | 0.452 | 175.8 |
| 3 | `rrf_p1_bm25` | 2.029 | 0.400 | 61.5 |
| 4 | `rrf_baseline_qdrant_bm25` | 1.946 | 0.381 | 45.2 |
| 5 | `rrf_p1_splade` | 1.932 | 0.368 | 150.5 |
| 6 | `rrf_p3_tfidf` | 1.919 | 0.419 | 66.1 |
| 7 | `rrf_p2_tfidf` | 1.873 | 0.374 | 163.2 |
| 8 | `rrf_p1_tfidf` | 1.516 | 0.265 | 54.2 |

