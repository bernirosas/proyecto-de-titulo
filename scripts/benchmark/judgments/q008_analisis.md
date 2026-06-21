# Análisis del juicio LLM — q008

**Query**: *"Rescisión de la compraventa de un bien raíz por lesión enorme y el justo precio"*
**Área**: Compraventa de bienes raíces
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-13
**Chunks evaluados**: 45

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 5 | 11% |
| 2 (relevante) | 5 | 11% |
| 1 (marginal) | 13 | 29% |
| 0 (irrelevante) | 22 | 49% |
| -1 (parse error) | 0 | 0% |

Distribución desplazada hacia abajo (49% grado 0, solo 10 chunks ≥2). Es coherente con la cobertura del corpus: "lesión enorme" aparece literalmente en apenas 9 chunks (medido con match_phrase). La lesión enorme es un remedio civil puro que el corpus, mayormente tributario, casi no discute; el pool se llena de oficios SII sobre tributación de la enajenación (grado 0/1) y solo un núcleo del Código Civil/Comercio responde de verdad. Los 10 relevantes son suficientes para discriminar, pero es la query más exigente del set.

## Aciertos

- `aafc8923` (g3): cita directamente el artículo que permite la rescisión de la compraventa por lesión enorme.
- `814fb353` (g3): define la lesión enorme en la compraventa para vendedor y comprador y el concepto de justo precio.
- `63864c99` (g3): define el derecho a completar el justo precio o restituir el exceso (art. 1890 CC).

Los grado 0 son correctos y revelan el ruido del dominio: tributación de la enajenación de bienes raíces (`1b59d97c`), habitualidad (`dfb060b4`), venta en contexto de leasing (`99204f8e`) — todos hablan de compraventa de inmuebles pero no de la rescisión por lesión.

## Inconsistencias detectadas

Sin errores objetivos. El alto grado 1 (29%) recoge oficios que mencionan "justo precio" o "rescisión" en sentido tributario y no civil; su clasificación marginal es correcta. **Correcciones manuales: 0.**

## Cobertura de grados

Los cuatro grados presentes. La concentración en grado 0 no es un defecto del juez sino reflejo fiel de que el concepto está poco representado en el corpus.

## Resultados de `evaluate_query.py`

**Técnica ganadora por top-10 mean_grade: `p1_bm25` (2.400)**, empatada con `p2_bm25` y `p3_bm25` (2.400).

| Observación | Detalle |
|---|---|
| BM25 domina con claridad | las tres variantes en 2.400; P@5 0.80 en p1/p2 |
| **SPLADE se queda corto** | 1.200 top-10 — **la mitad que BM25** |
| Baseline Qdrant muy bajo | 0.500 top-10 |
| TF-IDF inestable | p1_tfidf cae a 0.500; p3_tfidf top-1 perfecto pero decae |

**Es la query más valiosa del set para la tesis.** Confirma la hipótesis del eje BM25 vs SPLADE: ante un término jurídico raro y preciso ("lesión enorme"), el match léxico exacto sobre el Código Civil/Comercio recupera los artículos correctos, mientras que la expansión semántica de SPLADE deriva hacia el ruido tributario y rinde la mitad. Es exactamente el tipo de consulta "ambigua entre técnicas" que la guía premia.

## Conclusión

Juicios utilizables como ground truth. Aunque la distribución está sesgada a grado 0 (esperable por la baja cobertura del concepto), el núcleo de 10 relevantes está bien clasificado y la query produce la señal experimental más fuerte del set (BM25 ≫ SPLADE). Se procede sin correcciones.
