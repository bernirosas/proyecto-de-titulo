# Análisis del juicio LLM — q013

**Query**: *"Crédito fiscal del IVA en los gastos de administración de un edificio"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-09
**Chunks evaluados**: 49

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 3 | 6% |
| 2 (relevante) | 35 | 71% |
| 1 (marginal) | 9 | 18% |
| 0 (irrelevante) | 2 | 4% |
| -1 (parse error) | 0 | 0% |

La distribución se aparta del rango objetivo definido en el prompt ("20-30% grado 3, mayoría en grado 2"). Aquí el grado 3 cae a apenas 6% (3 de 49) mientras que el grado 2 concentra el 71% del pool (35 de 49). En otras palabras, el juez fue extremadamente conservador en el extremo alto: clasificó casi todo el corpus tributario recuperado como "relevante" pero casi nada como "altamente relevante".

Este patrón tiene una lectura crítica importante. Por un lado, es esperable para un tema acotado: la query toca un nicho (IVA, crédito fiscal, gastos de administración de un edificio) sobre el que el corpus tiene muchos oficios, resoluciones y jurisprudencia que hablan de crédito fiscal del IVA en general, todos genuinamente "relevantes pero no estelares". Por otro lado, esa misma uniformidad delata que el juez casi no discriminó entre un chunk que responde directamente la pregunta (gastos comunes / administración del edificio) y uno que solo comparte el dominio (crédito fiscal del IVA en construcción o arriendo). El resultado es una capa de grado 2 muy ancha y poco informativa.

La consecuencia práctica es que P@k (que solo cuenta grado 3) queda casi aplanado: con solo 3 chunks de grado 3 en todo el pool, la métrica de precisión tiene muy poca señal para separar técnicas, y el peso del análisis recae sobre el `mean_grade`.

## Aciertos

Los tres grado 3 son clasificaciones sólidas: corresponden a oficios que sí abordan el derecho a crédito fiscal del IVA sobre adquisiciones destinadas a activo fijo y gastos generales, que es el corazón conceptual de la consulta:

- `93f12d5e`: explica el derecho a crédito fiscal del IVA por adquisición de bienes y servicios destinados a formar parte del activo fijo o gastos generales. Es el chunk más alineado con "gastos de administración".
- `9fb13b41`: analiza el derecho a crédito fiscal por construcción de inmuebles y su destino a operaciones gravadas o no gravadas.
- `8d189086`: oficio que consulta sobre la procedencia del crédito fiscal IVA en la construcción de un inmueble comercial.

Los dos grado 0 son descartes correctos: ninguno guarda relación con el crédito fiscal del IVA en gastos de administración.

- `000a732d`: trata sobre la prueba en materia de inversiones y gastos de vida, no sobre crédito fiscal de IVA.
- `00045cfe`: trata sobre la clasificación de bienes raíces y avalúos fiscales, no sobre el crédito fiscal del IVA en gastos de administración.

## Inconsistencias detectadas

Con 35 chunks apretados en el grado 2, la principal inconsistencia no son grados sueltos mal puestos sino una frontera 2-vs-3 mal calibrada. El caso más claro es `c333ebc6`:

- `c333ebc6` (grado 2): *"aclara que la distribución de gastos comunes no es hecho gravado y el IVA no es crédito fiscal para la empresa administradora"*.

Este chunk responde de forma directa y específica el escenario de la query (gastos comunes / administración del edificio frente al crédito fiscal del IVA) y, sin embargo, recibió grado 2, el mismo que decenas de chunks genéricos sobre crédito fiscal del IVA. Bajo la rúbrica del prompt debería estar a la altura de los grado 3, o incluso por encima de ellos en pertinencia para esta query puntual.

El mismo aplanamiento aparece en pares de justificaciones casi equivalentes que reciben el mismo grado 2 pese a tener distinta cercanía al tema "administración de edificio":

- `0d91f331` (grado 2): *"discute el uso del crédito fiscal del IVA en bienes de uso común y la proporcionalidad, relevante para gastos de administración"* — la propia justificación lo declara relevante para gastos de administración.
- `8aa306be` (grado 2): *"aborda el crédito fiscal IVA en la construcción de un edificio para arrendamiento, lo cual se relaciona con gastos de administración"*.

Ambos invocan explícitamente los "gastos de administración" en su justificación, igual que los grado 3, pero quedaron un escalón abajo. Esto confirma que la frontera 2-vs-3 quedó mal calibrada: el juez reservó el grado 3 casi al azar para tres oficios sobre activo fijo/construcción y no premió a los chunks que más directamente tocan el escenario de la copropiedad.

Caso aparte de procesamiento: `a6dc5f36` aparece con la nota `[corregido manualmente: parse error del juez (-1); juzgado a criterio con la misma rúbrica]` y quedó en grado 2. Es la única corrección manual del pool; no afecta la distribución final de grados (cero -1 efectivos) y su grado 2 es razonable.

## Ausencia / particularidad de algún grado

La particularidad de q013 es doble: cuasi-ausencia de grado 3 (solo 6%) y escasez de grado 0 (solo 4%). El pool está fuertemente cargado hacia el centro (grados 2 y 1 suman el 89%).

Esto es coherente con el tema: el retrieval esparso sobre "crédito fiscal del IVA" trae masivamente documentos tributarios genuinamente relacionados, por lo que casi no hay chunks completamente ajenos que merezcan grado 0. A la vez, son muy pocos los que responden con precisión quirúrgica la combinación específica "crédito fiscal + gastos de administración de un edificio", de ahí los escasos grado 3. El grado 1 sí aparece de forma sana (9 chunks), capturando la zona tangencial — exportaciones de servicios (`cac5097a`), estacionamientos (`000747e9`), actividad agrícola (`8b77771e`), Ley Austral para construcción (`c17b2e86`) — que comparte vocabulario IVA/crédito fiscal pero se aleja del foco de la query.

## Resultados de `evaluate_query.py`

La técnica ganadora por `top-10 mean_grade` es **p1_bm25 (2.20)**. Sin embargo, el dato más relevante de esta evaluación es la **baja discriminación entre técnicas**: BM25, SPLADE y TF-IDF convergen en un rango muy estrecho de 1.9 a 2.2 de `top-10 mean_grade` (p1_splade 1.90, p2_bm25 / p3_bm25 2.10, p2_tfidf / p3_tfidf 1.90, con p1_tfidf 1.60 como único algo más bajo). Las técnicas quedan prácticamente empatadas dentro del ancho de la capa de grado 2.

P@k refuerza el diagnóstico: con solo 3 grado 3 en todo el corpus, la precisión es casi nula salvo aciertos puntuales (p1_bm25 top-5 P@k 0.40, p1_bm25 top-10 P@k 0.30). El baseline de Qdrant queda muy por detrás (`top-10 mean_grade` 0.333), confirmando que las técnicas esparsas del pipeline sí superan al baseline, pero sin distinguirse entre sí.

En términos experimentales, esto significa que q013 confirma que las técnicas esparsas recuperan documentación tributaria pertinente, pero **aporta poca señal para decidir cuál técnica es mejor**: el `mean_grade` está dominado por una capa de grado 2 que el juez asignó de forma casi homogénea.

## Conclusión

Los juicios son utilizables como ground truth para esta query: no hay parse errors efectivos, los extremos (grado 0 y grado 3) están bien clasificados, el grado 1 captura sanamente la zona tangencial, y la única corrección manual está documentada. En ese sentido, los grados son confiables.

Sin embargo, q013 discrimina mal entre técnicas. El juez aplastó el 71% del pool en grado 2 sin separar los chunks que responden directamente la pregunta (gastos comunes / administración) de los que solo comparten dominio (IVA en construcción o arriendo), lo que aplana P@k y deja a BM25, SPLADE y TF-IDF prácticamente empatadas. La query sirve como evidencia de que las técnicas esparsas superan al baseline, pero su valor para elegir una técnica ganadora es bajo.

Recomendación: conservar la query como ground truth válido, pero documentar explícitamente su baja capacidad discriminante. Si se quisiera convertir en una query de mayor valor experimental, convendría afinar el `query_text` para forzar el foco en el escenario de copropiedad (p. ej. enfatizar "gastos comunes" y "comunidad / administrador del edificio") y, en una iteración futura, ajustar el prompt para que el grado 3 premie la respuesta directa al escenario y no solo el dominio general del IVA.
