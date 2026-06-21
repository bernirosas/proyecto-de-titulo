# Análisis del juicio LLM — q012

**Query**: *"Tributación de la comunidad de copropietarios de un edificio"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-09
**Chunks evaluados**: 31

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 8 | 26% |
| 2 (relevante) | 15 | 48% |
| 1 (marginal) | 4 | 13% |
| 0 (irrelevante) | 4 | 13% |
| -1 (parse error) | 0 | 0% |

La distribución está dentro del rango objetivo definido en el prompt ("no más del 20-30% debería ser grado 3"): el grado 3 representa el 26% del pool. La mayor masa se concentra en el grado 2 (48%), lo que es esperable en una consulta de dominio acotado donde abundan los oficios del SII que tratan la tributación de comunidades desde un ángulo específico (IVA, arriendo de bienes comunes, administración) sin ser la respuesta directa y completa que define al grado 3. A diferencia de q001, esta query sí pobló los grados intermedios 1 y 0, que aquí reciben 4 chunks cada uno.

## Aciertos

Los grado 3 más fuertes corresponden a fragmentos que efectivamente definen la situación tributaria de la comunidad de copropietarios como contribuyente:

- `ab54d626`: explica que las comunidades no tienen personalidad jurídica y que los comuneros son los contribuyentes por la proporción de las rentas. Es el núcleo doctrinario de la consulta.
- `b529f96f`: explica el tratamiento tributario de las rentas de una comunidad, indicando que puede ser contribuyente del IDPC.
- `7b21ef36`: explica que las comunidades de edificios pueden actuar como contribuyentes de Primera Categoría si desarrollan una actividad empresarial, detallando sus obligaciones.
- `4ff90615`: explica detalladamente las obligaciones tributarias de una comunidad de copropietarios que arrienda espacios comunes, actuando como contribuyente de Primera Categoría.

Los grado 0 son clasificaciones correctas: `92aa8b2b` trata convenios de coordinación para avalúo y regularización de títulos de propiedad, y `a6579e3a` describe un programa de apoyo para la Operación Renta en edificios. Ninguno aborda la tributación de la comunidad propiamente tal, aunque comparten vocabulario de superficie ("propiedad", "edificios") con la query.

## Inconsistencias detectadas

Se observan pares de chunks con justificaciones casi equivalentes que reciben grados distintos en la frontera entre grado 2 y grado 3:

- `dd685307` (grado 3): *"aborda la tributación de una comunidad de edificio por arriendo de espacios comunes, definiendo su naturaleza jurídica y tratamiento tributario"*.
- `af85ee96` (grado 2): *"aborda las obligaciones tributarias de una comunidad de copropietarios que obtiene ingresos del arrendamiento de parte del inmueble común, remitiendo a oficios anteriores"*.

Ambos tratan el mismo supuesto (arriendo de bienes comunes por la comunidad) y la diferencia que parece haber pesado en el juez es que `af85ee96` remite a oficios anteriores en lugar de desarrollar la doctrina, una distinción de matiz más que de relevancia. El mismo patrón aparece entre `4ba09d6a` (grado 3, *"explica la tributación de las comunidades de copropietarios por arriendo de bienes comunes, incluyendo Impuesto a la Renta y IVA"*) y `579d2396` (grado 2, *"informa que una comunidad de copropietarios que arrienda espacios comunes puede ser contribuyente de Primera Categoría"*).

Esta variabilidad es ruido inherente al método LLM-as-judge en la zona limítrofe 2/3, no un defecto del pipeline. Para mitigarlo se recomienda, en trabajo futuro, medir agreement entre dos corridas independientes o entre dos jueces distintos. No se detectaron casos graves de un grado 3 que debiera ser 0, ni de un grado 0 que tratara directamente la consulta.

## Particularidad de los grados 1 y 0

A diferencia de q001 (donde el grado 1 quedó vacío), esta query sí pobló los cuatro grados, aunque el 1 y el 0 son pocos (4 chunks cada uno). El grado 1 captura chunks tangencialmente relacionados que tocan el tema de copropiedad o de impuestos sin responder la consulta: `1df5e95d` (contribución a expensas comunes y distribución de gastos), `a209a54b` (modificaciones a la Ley de Renta sobre regímenes y créditos, sin abordar comunidades) y `766edb1e` (determinación del capital propio de sociedades de personas). Estas clasificaciones son coherentes: son chunks que un retriever léxico puede traer por solapamiento de vocabulario pero que no aportan la respuesta, exactamente el tipo de caso que justifica la existencia del grado 1. Su presencia confirma que el prompt distingue la zona intermedia cuando el pool la contiene.

## Resultados de `evaluate_query.py`

La técnica ganadora por `top-10 mean_grade` es **`p3_tfidf` (2.60)**, seguida de `p2_tfidf` (2.50). Las variantes TF-IDF lideran por sobre las BM25 (`p1_bm25`, `p2_bm25` y `p3_bm25` empatan en ~2.40), de modo que la query discrimina moderadamente y favorece al ponderado TF-IDF en esta consulta de vocabulario tributario denso. `p1_splade` parte fuerte (top-1 mean 3.00, P@1 = 1.00) pero degrada hacia el top-10 (1.80), y `p1_tfidf` es la peor del conjunto (top-10 mean 1.20).

El hallazgo más relevante del experimento es que la técnica **`baseline_qdrant_bm25` devolvió 0 hits** para esta query: su ranking quedó vacío y por eso su `mean_grade` aparece como `—` (None) en el eval, no como 0. No es un empate ni un puntaje bajo, sino un fracaso total de recuperación: el BM25 del Qdrant del cliente no trajo ningún documento del pool (verificado re-ejecutando el retrieval en vivo). Es un dato válido y útil para la tesis, porque evidencia que la línea base del cliente puede colapsar por completo en consultas de este dominio, mientras que las técnicas propias del benchmark sí recuperan material relevante.

## Conclusión

Los juicios son utilizables como ground truth para esta query. La distribución cumple el criterio de conservadurismo del prompt (26% en grado 3), los cuatro grados están poblados de forma coherente, los extremos del pool (grado 3 y grado 0) están correctamente clasificados, y el ruido observado se limita a la frontera 2/3 dentro del rango esperado para un juez LLM single-pass. No hubo parse errors (-1) ni se requirieron correcciones manuales.

Se procede a la evaluación de las técnicas de retrieval con `evaluate_query.py`, cuyo ganador (`p3_tfidf`, 2.60) y el fracaso de `baseline_qdrant_bm25` (0 hits) ya quedaron documentados arriba.
