# Análisis del juicio LLM — q019

**Query**: *"¿En qué casos el arriendo de un inmueble está afecto a IVA?"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-11
**Chunks evaluados**: 57

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 19 | 33% |
| 2 (relevante) | 20 | 35% |
| 1 (marginal) | 9 | 16% |
| 0 (irrelevante) | 9 | 16% |
| -1 (parse error) | 0 | 0% |

Distribución muy sana con todos los grados representados y sin parse errors. El pool es el más grande de las 5 queries (57 chunks), lo que refleja que "arriendo de inmueble" + "IVA" tiene alta cobertura en el corpus: circulares, oficios y jurisprudencia abordan extensamente el Art. 8 letra g) del D.L. 825.

## Aciertos

Los grado 3 más sólidos:

- `3646fce4` (Oficio N°67/2022): explica que el factor determinante para la afectación a IVA del arriendo no es el destino del inmueble sino si cuenta con muebles o instalaciones especiales — responde directamente la query con el criterio legal vigente.
- `daea3fdb` (Oficio N°2597/2021): detalla que el arrendamiento de inmuebles está afecto a IVA si tienen instalaciones o maquinarias que permiten el ejercicio de una actividad comercial o industrial — grado 3 bien asignado.

Los grado 0 son correctos: chunks sobre tributación en divisiones de sociedades (`dbc93d55`, `a26ed49b`) y sobre venta de inmuebles (no arriendo) son ajenos a la query.

## Inconsistencias detectadas

La distinción entre grado 2 y 3 en esta query es la frontera más disputada. Varios chunks de la Circular N°13/2016 (que regula el IVA en arriendos con opción de compra y en arriendos de inmuebles amoblados) recibieron grados distintos pese a tratar el mismo cuerpo normativo:

- `2a54ada0` (Circular N°13/2016, grado 2): "explica que el IVA afecta a contratos de arriendo con opción de compra sobre bienes inmuebles".
- `366106f6` (Circular N°13/2016, grado 1): "se refiere a exenciones de IVA en arriendos con opción de compra, no a los casos generales de afectación".

El juez distinguió entre la regla general (afectación) y las exenciones dentro del mismo documento. La distinción es técnicamente razonable pero produce variabilidad entre chunks del mismo cuerpo normativo.

## Resultados de evaluate_query.py

| Técnica | top-10 mean | top-10 P@k |
|---------|------------:|-----------:|
| **p2_bm25** | **2.400** | **0.400** |
| p1_splade | 2.100 | 0.400 |
| p1_bm25 | 2.100 | 0.300 |
| p2_tfidf | 2.100 | 0.600 |
| p3_bm25 | 2.200 | 0.200 |
| p3_tfidf | 1.900 | 0.200 |
| p1_tfidf | 1.800 | 0.200 |
| baseline_qdrant_bm25 | 1.100 | 0.300 |

**Técnica ganadora**: `p2_bm25` (2.400). Las métricas son relativamente compactas entre las técnicas principales (rango 1.900–2.400), lo que indica **discriminación moderada**. El top-5 de p2_tfidf tiene el P@k más alto en top-10 (0.600), aunque su mean es idéntico a p1_bm25. El baseline denso de Qdrant es el claro rezagado con solo 1.100. p1_splade arranca fuerte (grado 3 en top-1) pero cae en posiciones intermedias con grados 1, lo que baja su mean respecto a p2_bm25.

## Conclusión

Los juicios son utilizables como ground truth. La query es robusta: pool grande, distribución equilibrada entre los cuatro grados y cero parse errors. La discriminación moderada entre técnicas es esperable para un tema con alta cobertura léxica en el corpus — todos los buscadores encuentran "arriendo" + "IVA" con facilidad. El dato más útil para la tesis es el rezago sistemático del baseline denso de Qdrant, consistente con los resultados de q016 y q020.
