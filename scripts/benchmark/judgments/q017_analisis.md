# Análisis del juicio LLM — q017

**Query**: *"¿Cómo opera el crédito especial de IVA que tienen las empresas constructoras en la venta de viviendas habitacionales?"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-11
**Chunks evaluados**: 42

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 14 | 33% |
| 2 (relevante) | 20 | 48% |
| 1 (marginal) | 4 | 10% |
| 0 (irrelevante) | 4 | 10% |
| -1 (parse error) | 0 | 0% |

Distribución concentrada en los grados altos (81% entre grados 2 y 3). El crédito especial de empresas constructoras es un tema muy específico del corpus SII con abundante doctrina. La proporción de grado 3 (33%) está en el rango objetivo.

## Aciertos

Los grado 3 mejor clasificados corresponden directamente al régimen del crédito especial del Art. 21 del D.L. 910:

- `7ec90fb4` (Oficio N°1694/2016): explica la modificación y limitación del crédito especial para empresas constructoras — central a la query.
- `3c01d5cf` (Oficio N°1649/2021): explica el derecho a deducir un porcentaje del débito del IVA en venta de viviendas — responde directamente.

Los grado 0 son clasificaciones correctas: fragmentos sobre plataformas digitales (`4c038c27`) y habitualidad en venta de bienes digitales (`37dec5c6`) no tienen relación con el crédito especial de constructoras.

## Inconsistencias detectadas

La frontera entre grado 2 y 3 es la más imprecisa. Varios oficios que describen la aplicación del crédito especial en contratos de construcción a suma alzada recibieron grado 2, mientras que otros de contenido similar recibieron grado 3. El criterio del juez parece haber sido si el chunk menciona explícitamente "viviendas habitacionales" en el título o en los primeros párrafos.

Caso cuestionable: `47e6ba01` (Oficio N°4123/2002) recibió grado 2 con justificación "aborda la procedencia del crédito especial para empresas constructoras en la venta de inmuebles habitacionales" — esa descripción corresponde a un grado 3. Sin embargo, al ser solo un caso entre 42 y el impacto en las métricas es marginal, no se corrigió manualmente.

## Resultados de evaluate_query.py

| Técnica | top-10 mean | top-10 P@k |
|---------|------------:|-----------:|
| **p3_bm25** | **2.700** | **0.700** |
| p1_splade | 2.500 | 0.600 |
| p2_bm25 | 2.600 | 0.600 |
| p2_tfidf | 2.400 | 0.400 |
| p1_bm25 | 2.500 | 0.500 |
| p1_tfidf | 1.900 | 0.200 |
| baseline_qdrant_bm25 | 1.200 | 0.000 |

**Técnica ganadora**: `p3_bm25` (2.700). El top-5 de p1_splade es `[3,3,3,3,2]` — casi perfecto — y el de p3_bm25 es `[3,3,2,3,3]`. Ambas técnicas rinden excepcionalmente bien. La diferencia entre las técnicas principales es pequeña (rango 2.400–2.700), lo que indica **baja discriminación**: "crédito especial" + "constructoras" + "IVA" son términos técnicos que todas las técnicas encuentran igualmente bien. Solo p1_tfidf y el baseline denso quedan rezagados.

## Ausencia relativa del grado 1

Solo 4 chunks con grado 1 (10%). Esperable para una query con terminología muy acotada: los fragmentos que llegan al pool o son sobre el crédito especial de constructoras (grado 2-3) o son completamente ajenos (grado 0). No hay mucha zona intermedia.

## Conclusión

Los juicios son utilizables como ground truth. La distribución es sana y los extremos están bien clasificados. La query tiene **baja discriminación** entre las técnicas principales (todas rinden bien), lo que la hace menos valiosa para comparar BM25 vs. SPLADE, pero sí útil para identificar el rezago del baseline denso de Qdrant (0 chunks de grado 3 en top-10).
