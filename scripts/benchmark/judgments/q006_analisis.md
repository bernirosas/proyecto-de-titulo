# Análisis del juicio LLM — q006

**Query**: *"Requisitos y solemnidades de la escritura pública en la compraventa de bienes raíces"*
**Área**: Compraventa de bienes raíces
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-13
**Chunks evaluados**: 44

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 7 | 16% |
| 2 (relevante) | 12 | 27% |
| 1 (marginal) | 11 | 25% |
| 0 (irrelevante) | 14 | 32% |
| -1 (parse error) | 0 | 0% |

Distribución sana y con los cuatro grados poblados. A diferencia de q001/q000, aquí sí aparece una zona intermedia amplia (grado 1, 25%): el corpus tiene muchos chunks que mencionan "escritura pública" o "compraventa" en contexto tributario sin abordar el requisito de solemnidad civil, lo que produce relevancia tangencial legítima.

## Aciertos

Los grado 3 corresponden a fragmentos que efectivamente tratan la escritura pública como solemnidad de la compraventa de inmuebles:

- `235df7fe`: explica que la compraventa de bienes raíces requiere escritura pública como solemnidad para perfeccionarse.
- `6029a465`: define qué es una escritura pública y enumera las solemnidades legales.
- `d8702cb9`: establece que la adjudicación de bienes raíces debe reducirse a escritura pública para su inscripción.

Los grado 0 están correctamente descartados: habitualidad en la compraventa (`2afc9fcd`), arrendamiento y tributación (`754d8152`), tasación fiscal/municipal (`0bf34689`) — todos mencionan bienes raíces pero no la solemnidad consultada.

## Inconsistencias detectadas

No se detectaron errores objetivos que ameriten sobreescritura manual. La frontera grado 1 vs grado 2 concentra la subjetividad esperable: varios oficios SII que exigen instrumento público "para ciertas operaciones" quedaron en grado 1 por no referirse a la compraventa de inmuebles en particular, criterio que se considera correcto. **Correcciones manuales: 0.**

## Cobertura de grados

Los cuatro grados (0–3) están presentes; no hay ausencias que explicar. Es el comportamiento ideal para una query de concepto acotado pero con vocabulario frecuente en el corpus.

## Resultados de `evaluate_query.py`

**Técnica ganadora por top-10 mean_grade: `p2_bm25` (2.500)**, empatada con `p3_bm25` (2.500).

| Observación | Detalle |
|---|---|
| BM25 P2/P3 lideran | top-3 mean 3.0 y P@3 = 1.0 (los 3 primeros son grado 3) |
| SPLADE fuerte al inicio, decae | top-1 mean 3.0 y P@5 0.80, pero cae a 2.0 en top-10 |
| TF-IDF flojo | p1/p2_tfidf ≤ 1.4 en top-10 |
| Baseline Qdrant pésimo | 0.300 top-10 — no recupera los chunks de solemnidad |

Coincide con la intuición del paso de revisión: el match léxico sobre el Código Civil (BM25) gana, SPLADE acierta los primeros resultados por expansión semántica pero diluye después.

## Conclusión

Los juicios son utilizables como ground truth para esta query. Distribución equilibrada, extremos bien clasificados y discriminación clara entre familias de técnicas (BM25 > SPLADE > TF-IDF >> baseline). Se procede sin correcciones manuales.
