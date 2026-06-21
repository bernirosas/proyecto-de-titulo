# Análisis del juicio LLM — q020

**Query**: *"¿Puede deducirse como gasto tributario el impuesto territorial pagado por un inmueble destinado al giro de la empresa?"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-11
**Chunks evaluados**: 53

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 14 | 26% |
| 2 (relevante) | 12 | 23% |
| 1 (marginal) | 7 | 13% |
| 0 (irrelevante) | 20 | 38% |
| -1 (parse error) | 0 | 0% |

Distribución inusual: el grado 0 es el más frecuente (38%). Esto refleja que la query cruza dos dominios distintos — impuesto territorial (contribuciones) y gasto tributario en la Ley de la Renta — y el corpus tiene muchos chunks sobre cada uno por separado, pero pocos que conecten ambos. Los 20 chunks irrelevantes son documentos sobre donaciones, quiebras, depreciación y otros gastos sin relación con el impuesto territorial.

## Aciertos

Los grado 3 más sólidos:

- `d0e45278` (Oficio N°1183/2019): explica la deducción del impuesto territorial para empresas constructoras e inmobiliarias sobre bienes destinados al giro — responde directamente la query con el Art. 31 N°2 LIR.
- `f1665c3a` (TTA Región del Biobío): detalla los requisitos para deducir el impuesto territorial como crédito del impuesto de primera categoría — jurisprudencia directamente relevante.

Los grado 0 son clasificaciones correctas: chunks sobre donaciones (`a785de92`), sobre gastos en quiebra (`a4b7dfc4`) y sobre membresías digitales no tienen relación con el impuesto territorial como gasto tributario.

## Inconsistencias detectadas

La frontera entre grado 2 y 3 es la más difusa. Varios oficios sobre el impuesto territorial pagado *por el arrendatario* (y su tratamiento como mayor renta para el arrendador) recibieron grado 2:

- `754d8152` (Oficio N°2860/1996, grado 2): "aborda el tratamiento tributario del impuesto territorial pagado por el arrendatario".
- `56a96b8b` (Oficio N°1988/2020, grado 2): "indica que el impuesto territorial pagado por el arrendatario constituye mayor renta para el arrendador".

Estos chunks responden la pregunta de forma indirecta (desde la perspectiva del arrendatario, no del dueño del inmueble destinado al giro), por lo que grado 2 es razonable aunque no perfecto.

Caso cuestionable: el top-5 de p1_bm25 incluye un chunk con grado 0 en posición 3 (`posición 3: [3,3,0,2,3]`). Se trata de un documento sobre IVA en servicios digitales que comparte vocabulario de "gasto" con la query pero no tiene relación con impuesto territorial. Es un falso positivo léxico típico de BM25.

## Resultados de evaluate_query.py

| Técnica | top-10 mean | top-10 P@k |
|---------|------------:|-----------:|
| **p2_bm25** | **2.700** | **0.700** |
| p3_bm25 | 2.200 | 0.600 |
| p1_bm25 | 2.200 | 0.500 |
| p3_tfidf | 1.700 | 0.400 |
| p1_tfidf | 1.800 | 0.500 |
| p2_tfidf | 1.900 | 0.300 |
| p1_splade | 1.400 | 0.300 |
| baseline_qdrant_bm25 | 0.200 | 0.000 |

**Técnica ganadora**: `p2_bm25` (2.700). El top-5 de p2_bm25 es `[2,2,3,3,3]` — arranque moderado pero muy consistente hacia el final. En contraste, el top-5 de p1_splade es `[0,2,0,0,3]` — tres grados 0 en las primeras cuatro posiciones, el peor desempeño de SPLADE en las 5 queries. La hipótesis es que SPLADE expande "gasto tributario" hacia conceptos semánticamente relacionados (donaciones, créditos, depreciación) que son irrelevantes para esta query específica. El baseline denso de Qdrant fracasa completamente (0.200 mean, 0 chunks de grado 3 en top-10).

Esta query es la que **más discrimina** entre técnicas: diferencia de 2.500 puntos entre la ganadora (p2_bm25 = 2.700) y el peor resultado (baseline = 0.200).

## Conclusión

Los juicios son utilizables como ground truth. La alta proporción de grado 0 (38%) es esperada y no indica un problema de la query: refleja que el pool recuperó muchos documentos con vocabulario fiscal genérico que no responden la pregunta específica sobre impuesto territorial + gasto tributario. La query es la más discriminante del conjunto: muestra el límite de SPLADE cuando la expansión semántica genera ruido, y el colapso total del baseline denso de Qdrant en dominios técnico-legales muy específicos.
