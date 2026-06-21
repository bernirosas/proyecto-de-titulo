# Análisis del juicio LLM — q007

**Query**: *"Efectos y tratamiento del contrato de promesa de compraventa de un inmueble"*
**Área**: Compraventa de bienes raíces
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-13
**Chunks evaluados**: 35

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 7 | 20% |
| 2 (relevante) | 15 | 43% |
| 1 (marginal) | 1 | 3% |
| 0 (irrelevante) | 12 | 34% |
| -1 (parse error) | 0 | 0% |

Distribución bimodal (mucho grado 2 y grado 0, casi sin grado 1), igual patrón que q001: el pool se reparte entre chunks del dominio promesa/compraventa (≥2) y chunks completamente ajenos (0), sin apenas zona intermedia. 22 relevantes (≥2) sobre 35 es señal sólida.

## Aciertos

- `8f0cfd17` (g3): explica los efectos tributarios del contrato de promesa de compraventa de inmuebles.
- `abe0e09a` (g3): define el contrato de promesa y sus requisitos legales, vinculándolo con la compraventa.
- `3080c35c` (g3): tratamiento tributario de la enajenación de inmuebles adquiridos vía promesa y compraventa definitiva.

Los grado 0 son correctos: exenciones de IVA a embajadas (`178588af`, `11aebf3d`) e impuestos a rentas acumuladas/retiros (`1fda4e7c`), sin relación con la promesa.

## Inconsistencias detectadas

Sin errores objetivos. El único grado 1 del pool es coherente (mención tangencial). **Correcciones manuales: 0.**

## Ausencia del grado 1 (casi)

El grado 1 aparece una sola vez. Es esperable para una consulta cuyo tema (promesa de compraventa) está bien delimitado en el corpus: los chunks o son del dominio (≥2) o ajenos (0). No delata sesgo del prompt; replica lo observado en q001.

## Resultados de `evaluate_query.py`

**Técnica ganadora por top-10 mean_grade: `p3_tfidf` (2.500).**

| Observación | Detalle |
|---|---|
| Competencia muy pareja | seis técnicas entre 2.2 y 2.5 en top-10 |
| SPLADE competitivo | 2.400 top-10 — su mejor desempeño relativo de las 5 queries (la promesa admite match semántico) |
| TF-IDF P2/P3 destacan | p2/p3_tfidf con P@3 = 1.0 |
| Baseline Qdrant pésimo | 0.300 top-10 |

Es la query menos discriminante del set: SPLADE y las léxicas quedan casi empatadas, lo que sugiere que el vocabulario de "promesa de compraventa" es estable entre documento y consulta (poca ventaja para la expansión semántica, poca penalización para el match exacto).

## Conclusión

Juicios utilizables como ground truth. Baja discriminación entre técnicas (todas convergen en ~2.4), lo que en sí mismo es un dato: para temas de vocabulario estable, la elección de técnica importa poco. Se procede sin correcciones.
