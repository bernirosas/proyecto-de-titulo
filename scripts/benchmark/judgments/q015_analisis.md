# Análisis del juicio LLM — q015

**Query**: *"Asamblea de copropietarios y reglamento de copropiedad en la jurisprudencia"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-09
**Chunks evaluados**: 34

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 4 | 12% |
| 2 (relevante) | 9 | 26% |
| 1 (marginal) | 8 | 24% |
| 0 (irrelevante) | 13 | 38% |
| -1 (parse error) | 0 | 0% |

A diferencia de queries con tema tributario acotado (donde casi todo cae en grado 2), aquí los cuatro grados están bien repartidos y el grado 0 domina con 38% del pool. Esto no es una anomalía: es la señal de que el juez **sí discriminó**. El grado 3 se mantiene en un conservador 12%, por debajo del techo del 20-30% definido en el prompt, y existe una franja intermedia real de chunks marginales (grado 1, 24%) que para esta query tienen sentido —son fragmentos que tocan "copropiedad", "asamblea" o "reglamento" pero en un contexto ajeno (cooperativas de vivienda, asambleas de aportantes de fondos de inversión, copropiedad de acciones de sociedades). La abundancia de grado 0 refleja que gran parte del pool es ruido tributario sin relación con la consulta jurisprudencial.

## Aciertos

Los cuatro grado 3 son clasificaciones correctas y fuertes: corresponden a fragmentos de jurisprudencia y oficios que mencionan explícitamente la asamblea de copropietarios y/o el reglamento de copropiedad en el contexto de propiedad horizontal:

- `ae148832`: fragmento de jurisprudencia que menciona explícitamente la "Asamblea de copropietarios" en el contexto de permisos de obra y normativas urbanísticas.
- `4ff90615`: explica el fondo de reserva y menciona la asamblea de copropietarios y el reglamento interno.
- `ca5ce6ff`: oficio que menciona la citación y coordinación de asambleas de copropietarios y el reglamento de copropiedad en la administración de edificios.
- `64ee0920`: oficio sobre la inscripción de reglamentos de copropiedad y su relación con el pago de impuestos.

En el extremo opuesto, los grado 0 están bien descartados. Son chunks tributarios ajenos a la consulta:

- `e733cfc5`: sentencia tributaria que no menciona asambleas ni reglamentos de copropiedad.
- `766edb1e`: trata sobre la determinación del capital propio de sociedades.
- `a14d4e57`: se enfoca en la tributación de enajenación de acciones y el concepto de habitualidad.
- `6c5c4074`: oficio sobre tributación de seguros, sin relación con la consulta.

## Inconsistencias detectadas

El reparto es en general limpio, pero hay un caso de frontera 1/0 que merece atención. Varios chunks que sí mencionan "asamblea" pero en un contexto financiero (no inmobiliario) reciben tratamiento dispar:

- `00c68eca` (grado 1): *"Menciona 'asamblea de aportantes' y 'reglamento interno' en un contexto financiero, no de copropiedad inmobiliaria"*.
- `50c741e7` (grado 0): *"Este artículo de ley se refiere a asambleas extraordinarias de aportantes de fondos de inversión, no de copropiedad inmobiliaria"*.
- `41c1a14c` (grado 0): *"Este fragmento se refiere a asambleas de aportantes y comités de vigilancia, no a asambleas de copropietarios"*.

Las justificaciones son prácticamente equivalentes —todas describen "asambleas de aportantes" ajenas a la copropiedad inmobiliaria—, pero `00c68eca` recibió grado 1 y los otros dos grado 0. La diferencia parece deberse a que el primero también menciona "reglamento interno", lo que el juez interpretó como un roce léxico adicional. Es una inconsistencia menor, ruido inherente al método LLM-as-judge en la frontera marginal/irrelevante, sin impacto material sobre las métricas agregadas.

Caso aislado coherente pero discutible: `64183fdb` (grado 2) explica la naturaleza jurídica de la copropiedad inmobiliaria *"pero no aborda asambleas ni reglamentos"* según su propia justificación. Un grado 1 sería defendible al no tocar ninguno de los dos términos centrales de la query; aun así, por tratarse del dominio exacto (copropiedad inmobiliaria) el grado 2 es razonable.

## Particularidad: la abundancia del grado 0

Lo llamativo de esta query no es la ausencia de un grado, sino la dominancia del grado 0 (38%, el grado más numeroso). Es esperable: la consulta es jurisprudencial sobre propiedad horizontal, pero el corpus es mayoritariamente tributario (SII, oficios, sentencias tributarias, formularios). Un pool armado por retrieval esparso sobre ese corpus arrastra inevitablemente mucho fragmento irrelevante que comparte alguna palabra suelta ("copropiedad", "asamblea") sin relación real con el tema. Es una query "difícil": gran parte del pool es ruido, y el juez lo reflejó con honestidad en vez de inflar grados. La presencia simultánea de los cuatro grados confirma que el prompt no colapsó hacia un único valor.

## Resultados de `evaluate_query.py`

La técnica ganadora por `top-10 mean_grade` es **`p1_bm25` (1.90)**, empatada con `p2_bm25` (1.90) y seguida por las demás variantes léxicas (`p3_bm25` 1.80, `p3_tfidf` 1.70, `p2_tfidf` 1.60). Esta es la query de mayor valor experimental del set por tres hallazgos:

1. **El léxico vence al semántico, de forma nítida.** `p1_splade` es la **peor** técnica con `top-10 mean_grade` de **0.80** (la mitad del resto). En este dominio jurisprudencial, el match léxico exacto de "asamblea de copropietarios" y "reglamento de copropiedad" supera a la expansión semántica de SPLADE, que dispersa la consulta hacia términos vecinos y trae fragmentos tangenciales (asambleas de aportantes, copropiedad de acciones). Es el caso más discriminante del set: una brecha de más de un punto entre la mejor y la peor técnica.

2. **El baseline del cliente fracasa por completo.** `baseline_qdrant_bm25` devolvió **0 hits** (ranking vacío), por lo que su `mean_grade` aparece como `—` (None) en todos los `k`, no como 0. Se verificó re-ejecutando el retrieval en vivo: el BM25 del Qdrant del cliente no recupera ningún chunk útil para esta consulta. Es un dato válido y relevante para la tesis, no un error del pipeline.

3. **Coincide con la intuición del paso 5.3.** La query estaba marcada como candidata para mostrar discriminación entre técnicas (criterio 4 del README), y lo confirma con creces: separa las variantes léxicas del enfoque semántico y deja al baseline en evidencia.

## Conclusión

Los juicios son utilizables como ground truth para esta query. La distribución es sana (los cuatro grados presentes, grado 3 conservador en 12%, sin parse errors ni correcciones manuales), los extremos del pool están correctamente clasificados y el único ruido relevante está en la frontera marginal/irrelevante, dentro de lo esperado para un juez LLM single-pass.

Más aún, q015 es una de las queries más valiosas del set: discrimina nítidamente entre técnicas (criterio 4 del README), demuestra experimentalmente que el match léxico supera a la expansión semántica en jurisprudencia sobre propiedad horizontal, y documenta el fracaso del baseline del cliente. Se procede a registrar estos resultados.
