# Análisis del juicio LLM — q016

**Query**: *"Devolución del IVA en la venta de inmuebles nuevos"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-11
**Chunks evaluados**: 52

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 17 | 33% |
| 2 (relevante) | 18 | 35% |
| 1 (marginal) | 12 | 23% |
| 0 (irrelevante) | 5 | 10% |
| -1 (parse error) | 0 | 0% |

Distribución sana y bien calibrada. El 33% de grado 3 está en el límite superior esperado. La presencia de los cuatro grados indica que el juez discriminó correctamente entre chunks directamente sobre devolución de IVA en inmuebles, chunks sobre IVA en general, chunks tangenciales y chunks completamente ajenos.

## Aciertos

Los chunks de grado 3 más representativos son oficios SII sobre exenciones y devoluciones de IVA en inmuebles nuevos:

- `b675004a` (Oficio N°2953/2021): explica las exenciones de IVA para inmuebles nuevos y su aplicabilidad según fechas de construcción — responde directamente la query.
- `70b2b02c` (Oficio N°2953/2021): complementa el anterior detallando requisitos de construcción para la devolución — grado 3 justificado.

Los chunks de grado 0 están correctamente clasificados: un fragmento sobre IVA en arriendo de locales (`1790c0d2`) y otro sobre IVA en arriendo de oficinas (`13a01704`) son irrelevantes porque tratan arriendo, no venta de inmuebles nuevos.

## Inconsistencias detectadas

Los grados 1 son la zona más cuestionable: varios chunks sobre devolución de IVA bajo Art. 27 bis (remanentes de crédito fiscal en activos fijos) recibieron grado 1. Es un criterio razonable del juez — el Art. 27 bis es el mecanismo general de devolución de IVA, pero aplicado a activos fijos, no específicamente a la venta de inmuebles nuevos (que tiene su propio régimen). La distinción es técnicamente correcta.

Caso cuestionable: `d53a20c4` (Oficio N°2694/2020) recibió grado 2 con justificación sobre remanentes de IVA en activos fijos — debería ser grado 1 como sus pares del Art. 27 bis. El impacto sobre las métricas agregadas es marginal dado que hay 18 chunks en grado 2.

## Resultados de evaluate_query.py

| Técnica | top-10 mean | top-10 P@k |
|---------|------------:|-----------:|
| **p1_bm25** | **2.900** | **0.900** |
| p3_tfidf | 2.600 | 0.600 |
| p2_tfidf | 2.600 | 0.600 |
| p1_tfidf | 2.500 | 0.500 |
| p2_bm25 | 1.600 | 0.100 |
| p3_bm25 | 1.500 | 0.100 |
| p1_splade | 1.300 | 0.100 |
| baseline_qdrant_bm25 | 1.300 | 0.200 |

**Técnica ganadora**: `p1_bm25` (2.900). El top-5 de p1_bm25 es `[3,3,2,3,3]` — cuatro de los cinco primeros chunks son altamente relevantes. En contraste, p1_splade devuelve `[2,2,0,1,3]`, con un grado 0 en la tercera posición, lo que penaliza fuertemente sus métricas. La query discrimina muy bien: las técnicas BM25 con preprocesamiento P1 y las TF-IDF superan ampliamente a SPLADE y al baseline denso.

## Ausencia relativa del grado 0

Solo 5 chunks irrelevantes (10%) sobre 52. Esperable: el corpus del cliente está concentrado en materia tributaria inmobiliaria, por lo que casi todos los chunks recuperados tienen alguna relación con IVA o inmuebles. Los 5 que sí recibieron grado 0 corresponden a documentos sobre arriendo (no venta) o sobre impuestos distintos al IVA.

## Conclusión

Los juicios son utilizables como ground truth para esta query. La distribución es sana, los extremos están bien clasificados y la técnica ganadora (p1_bm25) coincide con la intuición: "devolución del IVA en inmuebles nuevos" usa terminología muy específica que BM25 encuentra con alta precisión en los títulos y texto de los oficios SII. La query discrimina fuertemente entre técnicas y aporta señal experimental valiosa para la tesis.
