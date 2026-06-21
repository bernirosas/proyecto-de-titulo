# Reporte sparse del benchmark

_Las 8 técnicas esparsas (P1/P2/P3 × BM25/TF-IDF + SPLADE + baseline_qdrant_bm25), aisladas del componente denso._

**Queries evaluadas**: 31 (7 temas representados)
**Métricas reportadas**: mean, mediana (p50), percentil 95

Las estadísticas son agregaciones cross-query: cada técnica recibe un valor por query (un `mean_grade@10`, un `P@5`, una latencia) y de esos valores se sacan mean / p50 / p95. Esto refleja cómo se comporta cada técnica en distintas consultas del dominio, no varianza intra-query.

## Resumen global

**Técnica ganadora**: `p3_bm25` (mean del `mean_grade@10` cross-query = 2.055)

### Calidad: `mean_grade @ top-10`

Promedio de la relevancia (escala 0-3) sobre los 10 primeros chunks.

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 2.055 | 2.100 | 2.600 | 31 |
| `p1_bm25` | 2.003 | 2.100 | 2.600 | 31 |
| `p2_bm25` | 1.961 | 2.100 | 2.600 | 31 |
| `baseline_qdrant_bm25` | 1.703 | 1.800 | 2.500 | 31 |
| `p3_tfidf` | 1.648 | 1.900 | 2.600 | 31 |
| `p2_tfidf` | 1.603 | 1.900 | 2.500 | 31 |
| `p1_splade` | 1.584 | 1.700 | 2.500 | 31 |
| `p1_tfidf` | 1.194 | 1.100 | 2 | 31 |

### Precisión: `P@5` (umbral estricto, grado = 3)

Fracción de los 5 primeros chunks que el juez consideró *altamente relevantes* (grado 3).

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 0.374 | 0.400 | 0.800 | 31 |
| `p1_bm25` | 0.368 | 0.400 | 0.800 | 31 |
| `p2_bm25` | 0.348 | 0.400 | 0.800 | 31 |
| `p3_tfidf` | 0.342 | 0.200 | 1.000 | 31 |
| `baseline_qdrant_bm25` | 0.335 | 0.200 | 0.800 | 31 |
| `p2_tfidf` | 0.303 | 0.200 | 0.800 | 31 |
| `p1_splade` | 0.258 | 0.200 | 0.800 | 31 |
| `p1_tfidf` | 0.155 | 0.000 | 0.600 | 31 |

### Latencia end-to-end (ms)

Tiempo de respuesta de cada técnica (preproc/encoder + I/O a OpenSearch). NO incluye highlights ni post-procesamiento.

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 8.0 | 13.5 | 8.8 | 31 |
| `p3_bm25` | 8.9 | 15.9 | 10.0 | 31 |
| `p2_tfidf` | 10.7 | 22.5 | 13.6 | 31 |
| `p2_bm25` | 11.4 | 23.6 | 12.8 | 31 |
| `baseline_qdrant_bm25` | 11.6 | 22.5 | 60.1 | 31 |
| `p1_bm25` | 13.0 | 18.5 | 14.6 | 31 |
| `p1_tfidf` | 13.1 | 19.8 | 13.4 | 31 |
| `p1_splade` | 103.9 | 165.9 | 218.0 | 31 |

## Desglose por tema

Para cada tema se reportan las mismas tres métricas. Si una técnica destaca en un tema pero no en otros, ahí está la pista experimental.

### Arrendamientos

**Queries**: `q001`, `q002`, `q003`, `q004`, `q005`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 1.300)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 1.300 | 1.800 | 1.900 | 5 |
| `p1_bm25` | 1.000 | 0.800 | 2 | 5 |
| `p2_bm25` | 0.860 | 0.600 | 2 | 5 |
| `p1_splade` | 0.820 | 0.900 | 1.600 | 5 |
| `p3_tfidf` | 0.700 | 0.400 | 2 | 5 |
| `p2_tfidf` | 0.580 | 0.400 | 2 | 5 |
| `baseline_qdrant_bm25` | 0.540 | 0.200 | 1.900 | 5 |
| `p1_tfidf` | 0.500 | 0.200 | 2 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_bm25` | 0.080 | 0.000 | 0.400 | 5 |
| `p1_splade` | 0.040 | 0.000 | 0.200 | 5 |
| `p2_bm25` | 0.040 | 0.000 | 0.200 | 5 |
| `p3_bm25` | 0.040 | 0.000 | 0.200 | 5 |
| `p3_tfidf` | 0.040 | 0.000 | 0.200 | 5 |
| `p1_tfidf` | 0.000 | 0.000 | 0.000 | 5 |
| `p2_tfidf` | 0.000 | 0.000 | 0.000 | 5 |
| `baseline_qdrant_bm25` | 0.000 | 0.000 | 0.000 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 9.3 | 15.8 | 10.7 | 5 |
| `p2_tfidf` | 10.7 | 20.2 | 12.8 | 5 |
| `p3_bm25` | 10.9 | 23.4 | 13.0 | 5 |
| `p2_bm25` | 11.2 | 23.6 | 13.3 | 5 |
| `baseline_qdrant_bm25` | 12.0 | 22.5 | 14.2 | 5 |
| `p1_tfidf` | 12.7 | 19.8 | 13.4 | 5 |
| `p1_bm25` | 13.0 | 17.5 | 14.6 | 5 |
| `p1_splade` | 107.0 | 165.9 | 125.0 | 5 |

### Compraventa

**Queries**: `q006`, `q007`, `q008`, `q009`, `q010`  (N = 5)
**Ganadora del tema**: `p2_bm25` (mean `mean_grade@10` = 2.500)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p2_bm25` | 2.500 | 2.500 | 2.700 | 5 |
| `p3_bm25` | 2.480 | 2.500 | 2.600 | 5 |
| `p1_bm25` | 2.340 | 2.300 | 2.800 | 5 |
| `p3_tfidf` | 2.060 | 2.500 | 2.700 | 5 |
| `p1_splade` | 1.980 | 2 | 2.600 | 5 |
| `p2_tfidf` | 1.920 | 1.900 | 2.700 | 5 |
| `baseline_qdrant_bm25` | 1.920 | 1.900 | 2.700 | 5 |
| `p1_tfidf` | 1.140 | 0.900 | 2.800 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p2_bm25` | 0.680 | 0.600 | 0.800 | 5 |
| `p3_bm25` | 0.640 | 0.600 | 0.800 | 5 |
| `p3_tfidf` | 0.640 | 0.600 | 1.000 | 5 |
| `baseline_qdrant_bm25` | 0.560 | 0.600 | 0.800 | 5 |
| `p1_bm25` | 0.520 | 0.600 | 0.800 | 5 |
| `p1_splade` | 0.520 | 0.400 | 0.800 | 5 |
| `p2_tfidf` | 0.480 | 0.600 | 0.600 | 5 |
| `p1_tfidf` | 0.240 | 0.200 | 0.800 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 7.2 | 8.9 | 6.7 | 5 |
| `p3_tfidf` | 7.2 | 8.7 | 6.8 | 5 |
| `p2_tfidf` | 8.3 | 10.4 | 8.4 | 5 |
| `p2_bm25` | 8.9 | 13.0 | 9.3 | 5 |
| `p1_bm25` | 11.4 | 18.5 | 12.4 | 5 |
| `baseline_qdrant_bm25` | 12.0 | 12.3 | 11.0 | 5 |
| `p1_tfidf` | 14.3 | 15.3 | 13.5 | 5 |
| `p1_splade` | 100.9 | 130.7 | 101.1 | 5 |

### Copropiedad / Propiedad horizontal

**Queries**: `q011`, `q012`, `q013`, `q014`, `q015`  (N = 5)
**Ganadora del tema**: `p1_bm25` (mean `mean_grade@10` = 2.120)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_bm25` | 2.120 | 2.100 | 2.400 | 5 |
| `p3_bm25` | 2.100 | 2.100 | 2.400 | 5 |
| `baseline_qdrant_bm25` | 2.060 | 2 | 2.400 | 5 |
| `p2_bm25` | 2.020 | 2 | 2.400 | 5 |
| `p3_tfidf` | 2.020 | 1.900 | 2.600 | 5 |
| `p2_tfidf` | 1.920 | 1.900 | 2.500 | 5 |
| `p1_splade` | 1.780 | 1.900 | 2.400 | 5 |
| `p1_tfidf` | 1.360 | 1.200 | 1.900 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_bm25` | 0.280 | 0.400 | 0.400 | 5 |
| `p2_bm25` | 0.280 | 0.400 | 0.400 | 5 |
| `p3_bm25` | 0.280 | 0.400 | 0.400 | 5 |
| `baseline_qdrant_bm25` | 0.280 | 0.200 | 0.800 | 5 |
| `p3_tfidf` | 0.200 | 0.200 | 0.400 | 5 |
| `p1_splade` | 0.160 | 0.200 | 0.400 | 5 |
| `p2_tfidf` | 0.160 | 0.200 | 0.400 | 5 |
| `p1_tfidf` | 0.120 | 0.000 | 0.400 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 6.9 | 10.6 | 7.8 | 5 |
| `p3_bm25` | 8.7 | 10.7 | 8.5 | 5 |
| `baseline_qdrant_bm25` | 8.7 | 12.9 | 9.6 | 5 |
| `p2_tfidf` | 10.2 | 13.5 | 9.9 | 5 |
| `p2_bm25` | 12.5 | 15.2 | 12.1 | 5 |
| `p1_bm25` | 12.7 | 17.3 | 13.5 | 5 |
| `p1_tfidf` | 13.1 | 16.1 | 12.3 | 5 |
| `p1_splade` | 85.1 | 135.3 | 98.4 | 5 |

### Tributación inmobiliaria

**Queries**: `q016`, `q017`, `q018`, `q019`, `q020`  (N = 5)
**Ganadora del tema**: `p1_bm25` (mean `mean_grade@10` = 2.360)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_bm25` | 2.360 | 2.200 | 2.900 | 5 |
| `p2_bm25` | 2.300 | 2.400 | 2.700 | 5 |
| `p2_tfidf` | 2.220 | 2.100 | 2.600 | 5 |
| `baseline_qdrant_bm25` | 2.160 | 2.100 | 2.500 | 5 |
| `p3_tfidf` | 2.140 | 2.100 | 2.600 | 5 |
| `p3_bm25` | 2.100 | 2.200 | 2.700 | 5 |
| `p1_tfidf` | 1.980 | 1.900 | 2.500 | 5 |
| `p1_splade` | 1.960 | 2.100 | 2.500 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p2_tfidf` | 0.560 | 0.600 | 0.800 | 5 |
| `p1_bm25` | 0.520 | 0.400 | 0.800 | 5 |
| `p3_tfidf` | 0.520 | 0.400 | 1.000 | 5 |
| `baseline_qdrant_bm25` | 0.480 | 0.400 | 0.800 | 5 |
| `p1_splade` | 0.400 | 0.400 | 0.800 | 5 |
| `p2_bm25` | 0.400 | 0.400 | 0.600 | 5 |
| `p3_bm25` | 0.400 | 0.200 | 0.800 | 5 |
| `p1_tfidf` | 0.320 | 0.200 | 0.600 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 9.0 | 16.1 | 9.7 | 5 |
| `p3_bm25` | 9.1 | 12.9 | 9.6 | 5 |
| `baseline_qdrant_bm25` | 11.9 | 22.1 | 13.8 | 5 |
| `p2_bm25` | 12.1 | 18.2 | 13.2 | 5 |
| `p2_tfidf` | 12.7 | 33.5 | 16.3 | 5 |
| `p1_tfidf` | 15.0 | 24.1 | 16.2 | 5 |
| `p1_bm25` | 15.1 | 32.6 | 17.3 | 5 |
| `p1_splade` | 108.0 | 169.6 | 112.0 | 5 |

### Recursos sobre bienes raíces

**Queries**: `q021`, `q022`, `q023`, `q024`, `q025`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 2.240)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 2.240 | 2.100 | 2.800 | 5 |
| `p1_bm25` | 2.160 | 2.200 | 2.600 | 5 |
| `p2_bm25` | 2.080 | 2.300 | 2.400 | 5 |
| `p2_tfidf` | 1.880 | 1.900 | 2.300 | 5 |
| `baseline_qdrant_bm25` | 1.860 | 1.800 | 2.300 | 5 |
| `p3_tfidf` | 1.840 | 1.700 | 2.600 | 5 |
| `p1_splade` | 1.700 | 1.900 | 2.300 | 5 |
| `p1_tfidf` | 0.960 | 1.100 | 1.700 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_bm25` | 0.480 | 0.400 | 0.800 | 5 |
| `p3_bm25` | 0.440 | 0.400 | 0.800 | 5 |
| `baseline_qdrant_bm25` | 0.440 | 0.400 | 1.000 | 5 |
| `p2_bm25` | 0.400 | 0.200 | 0.800 | 5 |
| `p3_tfidf` | 0.400 | 0.200 | 1.000 | 5 |
| `p2_tfidf` | 0.360 | 0.400 | 0.800 | 5 |
| `p1_splade` | 0.240 | 0.200 | 0.800 | 5 |
| `p1_tfidf` | 0.160 | 0.000 | 0.600 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 7.6 | 12.7 | 9.2 | 5 |
| `p2_bm25` | 12.0 | 26.2 | 14.3 | 5 |
| `p3_bm25` | 12.6 | 15.9 | 12.1 | 5 |
| `p1_tfidf` | 13.5 | 21.0 | 14.0 | 5 |
| `p1_bm25` | 15.2 | 17.4 | 14.1 | 5 |
| `baseline_qdrant_bm25` | 15.3 | 27.3 | 16.0 | 5 |
| `p2_tfidf` | 19.9 | 56.9 | 23.6 | 5 |
| `p1_splade` | 114.4 | 163.2 | 121.2 | 5 |

### Jurisprudencia de inmuebles

**Queries**: `q026`, `q027`, `q028`, `q029`, `q030`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 2.080)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 2.080 | 2 | 2.300 | 5 |
| `p1_bm25` | 1.980 | 2 | 2.300 | 5 |
| `p2_bm25` | 1.980 | 1.900 | 2.300 | 5 |
| `baseline_qdrant_bm25` | 1.560 | 1.500 | 1.800 | 5 |
| `p1_splade` | 1.080 | 0.800 | 2 | 5 |
| `p1_tfidf` | 1.060 | 1 | 1.500 | 5 |
| `p3_tfidf` | 0.960 | 0.800 | 2.200 | 5 |
| `p2_tfidf` | 0.920 | 0.900 | 1.600 | 5 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 0.440 | 0.400 | 0.600 | 5 |
| `p1_bm25` | 0.320 | 0.200 | 0.600 | 5 |
| `p2_bm25` | 0.280 | 0.200 | 0.600 | 5 |
| `baseline_qdrant_bm25` | 0.200 | 0.200 | 0.200 | 5 |
| `p2_tfidf` | 0.160 | 0.200 | 0.400 | 5 |
| `p3_tfidf` | 0.160 | 0.200 | 0.400 | 5 |
| `p1_splade` | 0.120 | 0.000 | 0.400 | 5 |
| `p1_tfidf` | 0.080 | 0.000 | 0.200 | 5 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 7.0 | 11.6 | 7.7 | 5 |
| `p3_bm25` | 7.3 | 9.3 | 7.1 | 5 |
| `baseline_qdrant_bm25` | 9.1 | 11.6 | 8.9 | 5 |
| `p2_bm25` | 9.3 | 11.4 | 9.5 | 5 |
| `p1_bm25` | 9.4 | 14.2 | 10.4 | 5 |
| `p1_tfidf` | 10.3 | 11.6 | 10.1 | 5 |
| `p2_tfidf` | 10.8 | 11.5 | 10.1 | 5 |
| `p1_splade` | 95.4 | 110.8 | 93.1 | 5 |

### Sanity check (seed)

**Queries**: `q000`  (N = 1)
**Ganadora del tema**: `p1_splade` (mean `mean_grade@10` = 2.500)

**Calidad** (`mean_grade@10`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p1_splade` | 2.500 | 2.500 | 2.500 | 1 |
| `p2_tfidf` | 2.500 | 2.500 | 2.500 | 1 |
| `p3_tfidf` | 2.500 | 2.500 | 2.500 | 1 |
| `p1_bm25` | 2.300 | 2.300 | 2.300 | 1 |
| `baseline_qdrant_bm25` | 2.300 | 2.300 | 2.300 | 1 |
| `p3_bm25` | 2.200 | 2.200 | 2.200 | 1 |
| `p2_bm25` | 2.100 | 2.100 | 2.100 | 1 |
| `p1_tfidf` | 2.000 | 2 | 2 | 1 |

**Precisión** (`P@5`):

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p2_tfidf` | 0.800 | 0.800 | 0.800 | 1 |
| `p3_tfidf` | 0.800 | 0.800 | 0.800 | 1 |
| `p1_splade` | 0.600 | 0.600 | 0.600 | 1 |
| `baseline_qdrant_bm25` | 0.600 | 0.600 | 0.600 | 1 |
| `p1_bm25` | 0.400 | 0.400 | 0.400 | 1 |
| `p2_bm25` | 0.400 | 0.400 | 0.400 | 1 |
| `p3_bm25` | 0.400 | 0.400 | 0.400 | 1 |
| `p1_tfidf` | 0.200 | 0.200 | 0.200 | 1 |

**Latencia** (ms):

| Técnica | p50 | p95 | mean | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 13.5 | 13.5 | 13.5 | 1 |
| `p2_tfidf` | 13.9 | 13.9 | 13.9 | 1 |
| `p1_tfidf` | 17.6 | 17.6 | 17.6 | 1 |
| `p3_bm25` | 26.6 | 26.6 | 26.6 | 1 |
| `p2_bm25` | 37.8 | 37.8 | 37.8 | 1 |
| `p1_bm25` | 41.2 | 41.2 | 41.2 | 1 |
| `baseline_qdrant_bm25` | 1495.5 | 1495.5 | 1495.5 | 1 |
| `p1_splade` | 3503.6 | 3503.6 | 3503.6 | 1 |

## Ranking final (calidad vs costo)

Tabla resumen que ordena las técnicas por calidad y muestra el costo asociado. Útil para argumentar trade-offs en la sección de discusión.

| Rank | Técnica | mean_grade@10 (mean) | P@5 (mean) | lat ms (p50) |
|---:|---|---:|---:|---:|
| 1 | `p3_bm25` | 2.055 | 0.374 | 8.9 |
| 2 | `p1_bm25` | 2.003 | 0.368 | 13.0 |
| 3 | `p2_bm25` | 1.961 | 0.348 | 11.4 |
| 4 | `baseline_qdrant_bm25` | 1.703 | 0.335 | 11.6 |
| 5 | `p3_tfidf` | 1.648 | 0.342 | 8.0 |
| 6 | `p2_tfidf` | 1.603 | 0.303 | 10.7 |
| 7 | `p1_splade` | 1.584 | 0.258 | 103.9 |
| 8 | `p1_tfidf` | 1.194 | 0.155 | 13.1 |

