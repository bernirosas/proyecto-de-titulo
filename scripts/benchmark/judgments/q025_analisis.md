# Análisis de retrieval — q025

**Query**: *"Tercería de dominio sobre inmueble embargado en juicio ejecutivo"*
**Judgments**: 39 chunks evaluados (1 chunk omitido por parse error del juez, ~2.5%)
**Ganador top-10**: `p2_bm25` (mean_grade 2.400, empatado con `p3_bm25` pero con mejor P@10)

## Resultados

| Técnica | top-1 | P@1 | top-3 | P@3 | top-5 | P@5 | top-10 | P@10 | lat (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **p2_bm25** | 3.000 | 1.000 | **3.000** | **1.000** | **2.800** | **0.800** | **2.400** | **0.600** | 26 |
| p3_bm25 | 3.000 | 1.000 | **3.000** | **1.000** | 2.600 | 0.800 | **2.400** | 0.500 | 46 |
| p2_tfidf | 3.000 | 1.000 | 2.667 | 0.667 | 2.600 | 0.600 | 2.300 | 0.500 | 26 |
| p1_bm25 | 1.000 | 0.000 | 2.333 | 0.667 | 2.400 | 0.600 | 2.200 | 0.400 | 64 |
| p3_tfidf | 3.000 | 1.000 | **3.000** | **1.000** | 2.400 | 0.600 | 2.200 | 0.500 | 21 |
| p1_splade | 3.000 | 1.000 | **3.000** | **1.000** | 2.800 | 0.800 | 2.000 | 0.400 | 3173 |
| p1_tfidf | 3.000 | 1.000 | 2.000 | 0.333 | 1.200 | 0.200 | 1.100 | 0.200 | 48 |
| baseline_qdrant_bm25 | 1.000 | 0.000 | 0.500 | 0.000 | 0.250 | 0.000 | 0.222 | 0.000 | 1383 |

## Observaciones

`p2_bm25` y `p3_bm25` empatan top-10 con mean_grade 2.400, pero `p2_bm25` toma la delantera por P@10 (0.600 vs 0.500) — entrega 6 hits altamente relevantes en 10 posiciones frente a 5. Es la segunda vez en el set (q021 fue la primera) que el preprocesamiento intermedio del pipeline 2 se impone, completando un patrón heterogéneo: cada uno de los tres pipelines gana al menos una query del área. **No hay un pipeline dominante** — el ganador depende de la query.

**Comportamiento anómalo de `p1_bm25`**: top-1=1.000 (un primer hit apenas tangencial), único caso del set donde una variante de BM25 falla la cabeza del ranking. Las otras 6 técnicas no-Qdrant convergen en top-1=3.000 con P@1=1.000. El ranking de `p1_bm25` se recupera hacia abajo (top-3=2.333, top-10=2.200) y termina competitivo, pero el desplazamiento del top-1 es inusual considerando que p1_bm25 ganó top-1 limpio en q021 y q022. El preprocesamiento básico falla acá donde p2 y p3 aciertan — posible interferencia de "tercería" o "embargado" en forma cruda con chunks no relacionados.

`p1_splade` reaparece con top-1=3.000 y top-3=3.000 perfectos, pero cae a 2.000 en top-10 — la cola del ranking se contamina. Suma 3173ms de latencia para terminar por debajo de `p3_tfidf` (21ms) en top-10. Trade-off consistentemente desfavorable a lo largo del set.

`baseline_qdrant_bm25` toca el piso histórico: **top-10=0.222**, el peor valor agregado de cualquier técnica en cualquier query del área. Top-1=1.000, P@k=0 en todos los cortes. Para una query con vocabulario procesal muy específico ("tercería de dominio", "juicio ejecutivo"), los embeddings densos generales devuelven ruido casi puro. Es la confirmación más contundente del problema del retrieval denso en este corpus.

## Cierre del set q021-q025

Con q025 cierran las cinco queries del área "Recursos sobre bienes raíces". **BM25 gana las cinco** (p2 en q021/q025, p1 en q022, p3 en q023/q024). Ninguna variante de TF-IDF, SPLADE o Qdrant denso encabeza un top-10. El pipeline ganador rota entre p1/p2/p3 sin patrón fijo. SPLADE entrega entre 30x y 70x más latencia que BM25 sin mejorar calidad agregada. Qdrant denso queda siempre en el fondo (top-10 entre 0.222 y 1.700, P@k=0 en cuatro de cinco queries). El corpus legal chileno favorece de forma consistente el matching léxico sobre la similitud semántica generalista.
