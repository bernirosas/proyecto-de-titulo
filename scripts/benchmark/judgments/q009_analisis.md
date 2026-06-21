# Análisis del juicio LLM — q009

**Query**: *"Obligación del vendedor de saneamiento de la evicción en la compraventa"*
**Área**: Compraventa de bienes raíces
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-13
**Chunks evaluados**: 42

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 9 | 21% |
| 2 (relevante) | 6 | 14% |
| 1 (marginal) | 5 | 12% |
| 0 (irrelevante) | 22 | 52% |
| -1 (parse error) | 0 | 0% |

Distribución con buen núcleo de altamente relevantes (9 grado 3, el más alto del set) y mitad del pool en grado 0. El saneamiento de la evicción es materia exclusivamente del Código Civil/Procedimiento Civil; el juez separó nítidamente esos artículos del ruido tributario.

## Aciertos

- `0d405f65` (g3): artículo del Código Civil que define la obligación del vendedor de sanear la evicción y sus excepciones.
- `05862f77` (g3): obligaciones del vendedor en caso de evicción, incluyendo restitución y perjuicios.
- `be4371f5` (g3): define la acción de saneamiento y su indivisibilidad.

Grado 0 correctos: modificaciones a la Ley de la Renta (`2dafb986`), compra de mercaderías a precio de otro (`b59f1b23`), retenciones en enajenación de acciones (`0f6fa7a4`).

## Inconsistencias detectadas

Sin errores objetivos. Nótese que el término "saneamiento de la evicción" aparece literalmente en 1 solo chunk, pero el concepto ("evicción", 22 chunks; citación de evicción en el CPC) está bien cubierto y el juez lo reconoció. **Correcciones manuales: 0.**

## Cobertura de grados

Los cuatro grados presentes con un grado 3 robusto (9 chunks). Sin ausencias que explicar.

## Resultados de `evaluate_query.py`

**Técnica ganadora por top-10 mean_grade: `p2_bm25` (2.500)**, empatada con `p3_bm25` y `p3_tfidf` (2.500).

| Observación | Detalle |
|---|---|
| Léxicas P2/P3 lideran | BM25 y TF-IDF con preprocesamiento P3 (Snowball) en 2.500 |
| SPLADE intermedio | 1.700 top-10 — por debajo de las léxicas, otra vez el código gana al match exacto |
| **p1_tfidf falla total** | 0.000 en todos los k: no recuperó ningún chunk relevante |
| Baseline Qdrant bajo | 0.400 top-10 (pese a un top-1 grado 3 puntual) |

Refuerza el patrón de q008: las obligaciones codificadas (saneamiento, evicción) favorecen el match léxico sobre el Código Civil. El fallo total de `p1_tfidf` (0.0) es un dato a destacar: el TF-IDF con preprocesamiento mínimo P1 no acertó ningún relevante para esta consulta.

## Conclusión

Juicios utilizables como ground truth. Núcleo de relevantes amplio y bien clasificado, discriminación clara (P3-léxicas > SPLADE >> p1_tfidf/baseline). Se procede sin correcciones.
