# Reporte consolidado del benchmark

**Queries evaluadas**: 31 (7 temas representados)
**Modelo juez (LLM)**: `gemini-2.5-flash-lite`
**Métricas reportadas**: mean, mediana (p50), percentil 95

Las estadísticas son agregaciones cross-query: cada técnica recibe un valor por query (un `mean_grade@10`, un `P@5`, una latencia) y de esos valores se sacan mean / p50 / p95. Esto refleja cómo se comporta cada técnica en distintas consultas del dominio, no varianza intra-query.

## Resumen global

**Técnica ganadora**: `p3_bm25` (mean del `mean_grade@10` cross-query = 2.055)

### Calidad: `mean_grade` por k (cross-query)

Promedio cross-query de la relevancia (escala 0-3) en los primeros k chunks, con k ∈ {1, 3, 5, 10}. Permite ver cómo cae la calidad a medida que aumenta k: una técnica con `top-1` alto pero `top-10` bajo concentra los relevantes al principio del ranking.

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 2.355 | 2.183 | 2.148 | 2.055 | 31 |
| `p1_bm25` | 2.161 | 2.129 | 2.129 | 2.003 | 31 |
| `p2_bm25` | 2.290 | 2.161 | 2.065 | 1.961 | 31 |
| `baseline_qdrant_bm25` | 2.097 | 2.011 | 1.910 | 1.697 | 31 |
| `p3_tfidf` | 2.226 | 1.925 | 1.826 | 1.648 | 31 |
| `p2_tfidf` | 1.903 | 1.796 | 1.735 | 1.603 | 31 |
| `p1_splade` | 1.774 | 1.720 | 1.703 | 1.584 | 31 |
| `p1_tfidf` | 1.806 | 1.452 | 1.297 | 1.194 | 31 |

### Calidad: `mean_grade @ top-10` (varianza)

Mismo `mean_grade@10` pero mostrando la varianza cross-query (mean / p50 / p95). Útil para distinguir técnicas con calidad media similar pero distinta robustez ante queries difíciles.

| Técnica | mean | p50 | p95 | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 2.055 | 2.100 | 2.600 | 31 |
| `p1_bm25` | 2.003 | 2.100 | 2.600 | 31 |
| `p2_bm25` | 1.961 | 2.100 | 2.600 | 31 |
| `baseline_qdrant_bm25` | 1.697 | 1.800 | 2.500 | 31 |
| `p3_tfidf` | 1.648 | 1.900 | 2.600 | 31 |
| `p2_tfidf` | 1.603 | 1.900 | 2.500 | 31 |
| `p1_splade` | 1.584 | 1.700 | 2.500 | 31 |
| `p1_tfidf` | 1.194 | 1.100 | 2 | 31 |

### Precisión: `P@k` por k (cross-query)

Fracción de los primeros k chunks que el juez consideró *altamente relevantes* (grado 3, umbral estricto), promediada cross-query. Sigue el mismo patrón de degradación que mean_grade.

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 0.484 | 0.419 | 0.374 | 0.313 | 31 |
| `p1_bm25` | 0.484 | 0.387 | 0.368 | 0.303 | 31 |
| `p2_bm25` | 0.516 | 0.387 | 0.348 | 0.303 | 31 |
| `p3_tfidf` | 0.548 | 0.398 | 0.342 | 0.265 | 31 |
| `p2_tfidf` | 0.419 | 0.355 | 0.303 | 0.239 | 31 |
| `baseline_qdrant_bm25` | 0.419 | 0.419 | 0.335 | 0.226 | 31 |
| `p1_splade` | 0.258 | 0.236 | 0.258 | 0.223 | 31 |
| `p1_tfidf` | 0.355 | 0.204 | 0.155 | 0.145 | 31 |

### Precisión: `P@5` (varianza)

Mismo `P@5` pero con varianza cross-query (mean / p50 / p95).

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

### Latencia end-to-end

Tiempo de respuesta de cada técnica (preproc/encoder + I/O a OpenSearch) en milisegundos. NO incluye highlights ni post-procesamiento. Se lidera con p50 porque la distribución tiene cola larga por cold-start de la primera query del proceso.

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 5.5 | 10.9 | 6.5 | 31 |
| `p3_bm25` | 6.2 | 14.8 | 11.2 | 31 |
| `baseline_qdrant_bm25` | 7.1 | 16.0 | 53.2 | 31 |
| `p2_bm25` | 7.4 | 13.3 | 9.1 | 31 |
| `p2_tfidf` | 7.7 | 13.0 | 8.7 | 31 |
| `p1_bm25` | 8.6 | 14.5 | 10.2 | 31 |
| `p1_tfidf` | 9.5 | 15.2 | 9.7 | 31 |
| `p1_splade` | 68.0 | 139.6 | 160.9 | 31 |

## Desglose por tema

Para cada tema se reportan las mismas tres métricas. Si una técnica destaca en un tema pero no en otros, ahí está la pista experimental.

### Arrendamientos

**Queries**: `q001`, `q002`, `q003`, `q004`, `q005`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 1.300)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 1.600 | 1.400 | 1.360 | 1.300 | 5 |
| `p1_bm25` | 0.800 | 1.133 | 1.160 | 1.000 | 5 |
| `p2_bm25` | 1.600 | 1.333 | 1.080 | 0.860 | 5 |
| `p1_splade` | 0.800 | 1.133 | 0.960 | 0.820 | 5 |
| `p3_tfidf` | 1.200 | 0.867 | 0.800 | 0.700 | 5 |
| `p2_tfidf` | 1.000 | 0.600 | 0.520 | 0.580 | 5 |
| `p1_tfidf` | 0.400 | 0.533 | 0.560 | 0.500 | 5 |
| `baseline_qdrant_bm25` | 0.600 | 0.467 | 0.520 | 0.500 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_bm25` | 0.000 | 0.067 | 0.080 | 0.080 | 5 |
| `p3_bm25` | 0.000 | 0.067 | 0.040 | 0.080 | 5 |
| `p3_tfidf` | 0.200 | 0.067 | 0.040 | 0.040 | 5 |
| `p1_splade` | 0.000 | 0.067 | 0.040 | 0.020 | 5 |
| `p2_bm25` | 0.200 | 0.067 | 0.040 | 0.020 | 5 |
| `p1_tfidf` | 0.000 | 0.000 | 0.000 | 0.000 | 5 |
| `p2_tfidf` | 0.000 | 0.000 | 0.000 | 0.000 | 5 |
| `baseline_qdrant_bm25` | 0.000 | 0.000 | 0.000 | 0.000 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 8.9 | 21.4 | 10.3 | 5 |
| `baseline_qdrant_bm25` | 11.4 | 20.0 | 12.6 | 5 |
| `p3_bm25` | 11.5 | 23.0 | 12.7 | 5 |
| `p1_tfidf` | 12.4 | 18.1 | 13.1 | 5 |
| `p1_bm25` | 12.7 | 22.4 | 13.5 | 5 |
| `p2_tfidf` | 13.0 | 30.0 | 15.2 | 5 |
| `p2_bm25` | 13.3 | 42.8 | 18.5 | 5 |
| `p1_splade` | 124.6 | 204.4 | 128.0 | 5 |

### Compraventa

**Queries**: `q006`, `q007`, `q008`, `q009`, `q010`  (N = 5)
**Ganadora del tema**: `p2_bm25` (mean `mean_grade@10` = 2.500)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p2_bm25` | 3.000 | 2.734 | 2.680 | 2.500 | 5 |
| `p3_bm25` | 3.000 | 2.734 | 2.640 | 2.480 | 5 |
| `p1_bm25` | 2.800 | 2.667 | 2.520 | 2.340 | 5 |
| `p3_tfidf` | 3.000 | 2.667 | 2.400 | 2.060 | 5 |
| `p1_splade` | 2.000 | 2.267 | 2.400 | 1.980 | 5 |
| `p2_tfidf` | 2.400 | 2.467 | 2.080 | 1.920 | 5 |
| `baseline_qdrant_bm25` | 2.800 | 2.533 | 2.320 | 1.920 | 5 |
| `p1_tfidf` | 2.200 | 1.667 | 1.360 | 1.140 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p2_bm25` | 1.000 | 0.734 | 0.680 | 0.540 | 5 |
| `p3_bm25` | 1.000 | 0.734 | 0.640 | 0.520 | 5 |
| `p3_tfidf` | 1.000 | 0.733 | 0.640 | 0.480 | 5 |
| `p1_bm25` | 0.800 | 0.667 | 0.520 | 0.420 | 5 |
| `p2_tfidf` | 0.800 | 0.733 | 0.480 | 0.400 | 5 |
| `p1_splade` | 0.200 | 0.467 | 0.520 | 0.380 | 5 |
| `baseline_qdrant_bm25` | 0.800 | 0.800 | 0.560 | 0.380 | 5 |
| `p1_tfidf` | 0.600 | 0.333 | 0.240 | 0.240 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 5.0 | 5.8 | 4.9 | 5 |
| `p3_bm25` | 5.7 | 6.7 | 5.4 | 5 |
| `p2_bm25` | 6.2 | 11.6 | 7.5 | 5 |
| `p2_tfidf` | 6.2 | 8.3 | 6.4 | 5 |
| `baseline_qdrant_bm25` | 7.1 | 8.4 | 7.3 | 5 |
| `p1_bm25` | 8.2 | 9.9 | 8.4 | 5 |
| `p1_tfidf` | 9.5 | 10.6 | 9.5 | 5 |
| `p1_splade` | 62.9 | 98.6 | 72.2 | 5 |

### Copropiedad / Propiedad horizontal

**Queries**: `q011`, `q012`, `q013`, `q014`, `q015`  (N = 5)
**Ganadora del tema**: `p1_bm25` (mean `mean_grade@10` = 2.120)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_bm25` | 2.400 | 2.333 | 2.240 | 2.120 | 5 |
| `p3_bm25` | 2.400 | 2.267 | 2.240 | 2.100 | 5 |
| `baseline_qdrant_bm25` | 2.200 | 2.333 | 2.160 | 2.060 | 5 |
| `p2_bm25` | 2.200 | 2.200 | 2.240 | 2.020 | 5 |
| `p3_tfidf` | 2.400 | 2.133 | 2.160 | 2.020 | 5 |
| `p2_tfidf` | 2.000 | 2.067 | 1.920 | 1.920 | 5 |
| `p1_splade` | 2.400 | 1.867 | 1.840 | 1.780 | 5 |
| `p1_tfidf` | 2.400 | 1.667 | 1.560 | 1.360 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_bm25` | 0.400 | 0.333 | 0.280 | 0.280 | 5 |
| `p3_bm25` | 0.400 | 0.267 | 0.280 | 0.240 | 5 |
| `p3_tfidf` | 0.400 | 0.200 | 0.200 | 0.220 | 5 |
| `p2_bm25` | 0.200 | 0.200 | 0.280 | 0.200 | 5 |
| `baseline_qdrant_bm25` | 0.200 | 0.333 | 0.280 | 0.200 | 5 |
| `p2_tfidf` | 0.200 | 0.267 | 0.160 | 0.180 | 5 |
| `p1_splade` | 0.400 | 0.200 | 0.160 | 0.140 | 5 |
| `p1_tfidf` | 0.400 | 0.133 | 0.120 | 0.080 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 5.2 | 6.5 | 5.5 | 5 |
| `baseline_qdrant_bm25` | 5.7 | 8.6 | 6.6 | 5 |
| `p2_tfidf` | 6.5 | 9.4 | 7.1 | 5 |
| `p2_bm25` | 7.0 | 8.7 | 7.2 | 5 |
| `p3_bm25` | 7.2 | 7.8 | 6.5 | 5 |
| `p1_tfidf` | 7.5 | 10.9 | 8.6 | 5 |
| `p1_bm25` | 8.5 | 9.8 | 8.8 | 5 |
| `p1_splade` | 68.5 | 118.0 | 76.9 | 5 |

### Tributación inmobiliaria

**Queries**: `q016`, `q017`, `q018`, `q019`, `q020`  (N = 5)
**Ganadora del tema**: `p1_bm25` (mean `mean_grade@10` = 2.360)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_bm25` | 2.800 | 2.267 | 2.400 | 2.360 | 5 |
| `p2_bm25` | 2.200 | 2.200 | 2.240 | 2.300 | 5 |
| `p2_tfidf` | 2.400 | 2.400 | 2.400 | 2.220 | 5 |
| `baseline_qdrant_bm25` | 2.200 | 2.333 | 2.320 | 2.160 | 5 |
| `p3_tfidf` | 2.400 | 2.333 | 2.360 | 2.140 | 5 |
| `p3_bm25` | 2.200 | 2.000 | 2.160 | 2.100 | 5 |
| `p1_tfidf` | 2.200 | 2.200 | 2.120 | 1.980 | 5 |
| `p1_splade` | 2.000 | 1.800 | 1.960 | 1.960 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_bm25` | 0.800 | 0.467 | 0.520 | 0.500 | 5 |
| `p2_bm25` | 0.400 | 0.400 | 0.400 | 0.440 | 5 |
| `p2_tfidf` | 0.800 | 0.600 | 0.560 | 0.440 | 5 |
| `baseline_qdrant_bm25` | 0.600 | 0.533 | 0.480 | 0.400 | 5 |
| `p1_splade` | 0.400 | 0.267 | 0.400 | 0.380 | 5 |
| `p3_tfidf` | 0.600 | 0.533 | 0.520 | 0.380 | 5 |
| `p1_tfidf` | 0.400 | 0.400 | 0.320 | 0.340 | 5 |
| `p3_bm25` | 0.400 | 0.400 | 0.400 | 0.340 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 5.7 | 7.5 | 6.0 | 5 |
| `p3_bm25` | 6.3 | 8.2 | 6.9 | 5 |
| `p2_tfidf` | 7.5 | 9.8 | 7.9 | 5 |
| `p2_bm25` | 7.6 | 9.4 | 7.8 | 5 |
| `baseline_qdrant_bm25` | 8.2 | 10.4 | 8.4 | 5 |
| `p1_bm25` | 10.0 | 10.7 | 9.5 | 5 |
| `p1_tfidf` | 10.5 | 12.2 | 10.9 | 5 |
| `p1_splade` | 65.1 | 75.6 | 67.6 | 5 |

### Recursos sobre bienes raíces

**Queries**: `q021`, `q022`, `q023`, `q024`, `q025`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 2.240)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 2.400 | 2.333 | 2.320 | 2.240 | 5 |
| `p1_bm25` | 2.400 | 2.267 | 2.280 | 2.160 | 5 |
| `p2_bm25` | 2.600 | 2.267 | 2.120 | 2.080 | 5 |
| `p2_tfidf` | 2.000 | 1.867 | 2.040 | 1.880 | 5 |
| `baseline_qdrant_bm25` | 2.400 | 2.467 | 2.200 | 1.860 | 5 |
| `p3_tfidf` | 2.600 | 2.200 | 1.960 | 1.840 | 5 |
| `p1_splade` | 2.000 | 1.867 | 1.680 | 1.700 | 5 |
| `p1_tfidf` | 2.000 | 1.533 | 1.200 | 0.960 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 0.400 | 0.467 | 0.440 | 0.380 | 5 |
| `p2_bm25` | 0.600 | 0.467 | 0.400 | 0.340 | 5 |
| `p1_bm25` | 0.600 | 0.467 | 0.480 | 0.320 | 5 |
| `p3_tfidf` | 0.600 | 0.533 | 0.400 | 0.300 | 5 |
| `p2_tfidf` | 0.400 | 0.333 | 0.360 | 0.280 | 5 |
| `p1_splade` | 0.400 | 0.333 | 0.240 | 0.260 | 5 |
| `baseline_qdrant_bm25` | 0.400 | 0.533 | 0.440 | 0.220 | 5 |
| `p1_tfidf` | 0.400 | 0.200 | 0.160 | 0.100 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_tfidf` | 5.0 | 6.2 | 4.7 | 5 |
| `p3_bm25` | 5.8 | 9.3 | 6.1 | 5 |
| `baseline_qdrant_bm25` | 6.3 | 8.1 | 6.4 | 5 |
| `p2_tfidf` | 6.4 | 10.1 | 7.1 | 5 |
| `p2_bm25` | 7.2 | 8.5 | 7.1 | 5 |
| `p1_tfidf` | 8.4 | 9.4 | 8.5 | 5 |
| `p1_bm25` | 8.6 | 9.3 | 8.2 | 5 |
| `p1_splade` | 62.9 | 75.3 | 63.8 | 5 |

### Jurisprudencia de inmuebles

**Queries**: `q026`, `q027`, `q028`, `q029`, `q030`  (N = 5)
**Ganadora del tema**: `p3_bm25` (mean `mean_grade@10` = 2.080)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 2.400 | 2.267 | 2.120 | 2.080 | 5 |
| `p1_bm25` | 1.600 | 2.000 | 2.120 | 1.980 | 5 |
| `p2_bm25` | 2.000 | 2.134 | 1.960 | 1.980 | 5 |
| `baseline_qdrant_bm25` | 2.200 | 1.733 | 1.800 | 1.560 | 5 |
| `p1_splade` | 1.200 | 1.267 | 1.200 | 1.080 | 5 |
| `p1_tfidf` | 1.600 | 0.933 | 0.800 | 1.060 | 5 |
| `p3_tfidf` | 1.600 | 1.200 | 1.080 | 0.960 | 5 |
| `p2_tfidf` | 1.400 | 1.200 | 1.240 | 0.920 | 5 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p3_bm25` | 0.600 | 0.533 | 0.440 | 0.300 | 5 |
| `p2_bm25` | 0.600 | 0.400 | 0.280 | 0.280 | 5 |
| `p1_bm25` | 0.200 | 0.266 | 0.320 | 0.220 | 5 |
| `baseline_qdrant_bm25` | 0.400 | 0.200 | 0.200 | 0.140 | 5 |
| `p3_tfidf` | 0.400 | 0.267 | 0.160 | 0.120 | 5 |
| `p1_tfidf` | 0.400 | 0.133 | 0.080 | 0.100 | 5 |
| `p1_splade` | 0.000 | 0.067 | 0.120 | 0.100 | 5 |
| `p2_tfidf` | 0.200 | 0.133 | 0.160 | 0.080 | 5 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p3_bm25` | 5.2 | 6.2 | 5.2 | 5 |
| `p3_tfidf` | 5.7 | 8.1 | 6.1 | 5 |
| `p2_bm25` | 5.8 | 7.5 | 6.1 | 5 |
| `p1_tfidf` | 6.5 | 7.8 | 6.7 | 5 |
| `baseline_qdrant_bm25` | 6.6 | 7.5 | 6.2 | 5 |
| `p1_bm25` | 6.9 | 8.5 | 6.9 | 5 |
| `p2_tfidf` | 8.0 | 11.3 | 8.3 | 5 |
| `p1_splade` | 61.8 | 82.4 | 65.7 | 5 |

### Sanity check (seed)

**Queries**: `q000`  (N = 1)
**Ganadora del tema**: `p1_splade` (mean `mean_grade@10` = 2.500)

**Calidad** (`mean_grade` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_splade` | 3.000 | 2.333 | 2.600 | 2.500 | 1 |
| `p2_tfidf` | 3.000 | 2.667 | 2.800 | 2.500 | 1 |
| `p3_tfidf` | 3.000 | 2.667 | 2.800 | 2.500 | 1 |
| `p1_bm25` | 3.000 | 2.667 | 2.400 | 2.300 | 1 |
| `baseline_qdrant_bm25` | 3.000 | 3.000 | 2.600 | 2.300 | 1 |
| `p3_bm25` | 3.000 | 2.667 | 2.400 | 2.200 | 1 |
| `p2_bm25` | 3.000 | 2.667 | 2.400 | 2.100 | 1 |
| `p1_tfidf` | 2.000 | 2.333 | 2.200 | 2.000 | 1 |

**Precisión** (`P@k` por k, cross-query del tema):

| Técnica | top-1 | top-3 | top-5 | top-10 | n |
|---|---:|---:|---:|---:|---:|
| `p1_splade` | 1.000 | 0.333 | 0.600 | 0.500 | 1 |
| `p2_tfidf` | 1.000 | 0.667 | 0.800 | 0.500 | 1 |
| `p3_tfidf` | 1.000 | 0.667 | 0.800 | 0.500 | 1 |
| `p3_bm25` | 1.000 | 0.667 | 0.400 | 0.400 | 1 |
| `p1_bm25` | 1.000 | 0.667 | 0.400 | 0.300 | 1 |
| `p2_bm25` | 1.000 | 0.667 | 0.400 | 0.300 | 1 |
| `baseline_qdrant_bm25` | 1.000 | 1.000 | 0.600 | 0.300 | 1 |
| `p1_tfidf` | 0.000 | 0.333 | 0.200 | 0.200 | 1 |

**Latencia** end-to-end:

| Técnica | p50 (ms) | p95 (ms) | mean (ms) | n |
|---|---:|---:|---:|---:|
| `p2_tfidf` | 10.2 | 10.2 | 10.2 | 1 |
| `p2_bm25` | 11.9 | 11.9 | 11.9 | 1 |
| `p3_tfidf` | 13.0 | 13.0 | 13.0 | 1 |
| `p1_tfidf` | 15.2 | 15.2 | 15.2 | 1 |
| `p1_bm25` | 40.7 | 40.7 | 40.7 | 1 |
| `p3_bm25` | 134.4 | 134.4 | 134.4 | 1 |
| `baseline_qdrant_bm25` | 1411.0 | 1411.0 | 1411.0 | 1 |
| `p1_splade` | 2616.2 | 2616.2 | 2616.2 | 1 |

## Ranking final (calidad vs costo)

Tabla resumen que ordena las técnicas por calidad y muestra el costo asociado. Útil para argumentar trade-offs en la sección de discusión.

| Rank | Técnica | mean_grade@10 (mean) | P@5 (mean) | latencia p50 (ms) |
|---:|---|---:|---:|---:|
| 1 | `p3_bm25` | 2.055 | 0.374 | 6.2 |
| 2 | `p1_bm25` | 2.003 | 0.368 | 8.6 |
| 3 | `p2_bm25` | 1.961 | 0.348 | 7.4 |
| 4 | `baseline_qdrant_bm25` | 1.697 | 0.335 | 7.1 |
| 5 | `p3_tfidf` | 1.648 | 0.342 | 5.5 |
| 6 | `p2_tfidf` | 1.603 | 0.303 | 7.7 |
| 7 | `p1_splade` | 1.584 | 0.258 | 68.0 |
| 8 | `p1_tfidf` | 1.194 | 0.155 | 9.5 |

