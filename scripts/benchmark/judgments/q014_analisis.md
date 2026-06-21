# Análisis del juicio LLM — q014

**Query**: *"Avalúo fiscal y reavalúo de condominios acogidos a la ley de copropiedad inmobiliaria"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-09
**Chunks evaluados**: 25

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 0 | 0% |
| 2 (relevante) | 17 | 68% |
| 1 (marginal) | 2 | 8% |
| 0 (irrelevante) | 6 | 24% |
| -1 (parse error) | 0 | 0% |

La distribución se aleja del rango objetivo del prompt ("mayoría en grado 2, no más del 20-30% en grado 3") por un motivo concreto: **el juez no asignó ningún grado 3**. La masa se concentra en el grado 2 (68%), con una cola de irrelevantes en grado 0 (24%) y apenas dos chunks marginales en grado 1.

La ausencia total de grado 3 es el hecho central de esta query. El grado 3 exige que el chunk responda "directa y exhaustivamente" a la consulta, y el juez consideró que ningún fragmento del pool alcanza ese estándar: hay mucho material que aborda el avalúo fiscal de condominios de forma correcta y pertinente (grado 2), pero no existe un chunk estelar que resuelva de lleno la pregunta combinada de avalúo *y reavalúo* de condominios acogidos a la ley de copropiedad. Esto tiene una consecuencia mecánica directa: como P@k usa el umbral `grado >= 3`, **P@k colapsa a 0 en todas las técnicas y todos los valores de k** (ver sección dedicada más abajo).

## Aciertos

Como no hay grado 3, los aciertos se ilustran con grado 2 sólidos y grado 0 bien descartados.

Grado 2 bien asignados (fragmentos que efectivamente tratan el procedimiento y los formularios del avalúo fiscal de condominios bajo la Ley de Copropiedad Inmobiliaria):

- `278c7e05`: *"explica el uso de formularios para el cálculo del avalúo fiscal en condominios acogidos a la ley de copropiedad inmobiliaria"*.
- `7be76a13`: *"explica los procedimientos para determinar el avalúo fiscal de bienes raíces acogidos a la Ley de Copropiedad Inmobiliaria"*.
- `69dc7412`: *"explica el procedimiento para determinar el avalúo fiscal de cada unidad en condominios acogidos a la Ley de Copropiedad Inmobiliaria"*.
- `25446216`: *"describe el cálculo del avalúo fiscal de unidades en condominios, diferenciando entre tipo A y B"*.

Grado 0 correctamente descartados (fragmentos ajenos por completo al avalúo de condominios):

- `001c8c50`: *"define actos judiciales no contenciosos y no tiene relación con avalúos fiscales de condominios"*.
- `000747e9`: *"trata sobre el IVA en el arrendamiento de estacionamientos, no sobre avalúos fiscales de condominios"*.
- `0004b1dd`: *"trata sobre exhumaciones y no tiene relación con avalúos fiscales de condominios"*.

Los extremos del pool están, por tanto, bien clasificados: lo que toca el tema alcanza grado 2 y lo que es ruido temático se va a grado 0.

## Inconsistencias detectadas

Con 17 chunks apilados en grado 2 conviene preguntarse si alguno merecía un 3 (lo que delataría un juez demasiado estricto en el extremo alto) o si hay mezcla entre el grado 2 y los marginales.

- Varios chunks de grado 2 declaran explícitamente que *reemplazan* o *actualizan* el procedimiento oficial para determinar el avalúo fiscal de bienes raíces acogidos a la Ley de Copropiedad Inmobiliaria: `9c0861a0` (*"reemplaza el procedimiento para determinar el avalúo fiscal..."*), `3fcf8a97` (*"actualiza los procedimientos..."*) y `d93cfad7` (*"reemplaza circulares anteriores y actualiza el procedimiento para el avalúo fiscal de condominios bajo la Ley de Copropiedad"*). Estos fragmentos describen de lleno la normativa de avalúo de condominios y son candidatos plausibles a grado 3; que el juez los mantenga todos en grado 2 sugiere un criterio conservador y uniforme en el extremo alto, más que un error puntual.

- Caso fronterizo en el otro extremo: `6a19e616` (grado 2) *"aborda la aplicación de exenciones de impuesto territorial a copropiedades inmobiliarias y la rebaja de avalúo fiscal"*. Toca copropiedad y avalúo, pero el eje es la exención de impuesto territorial, no el procedimiento de avalúo/reavalúo que pide la query; es más tangencial que el resto del grupo de grado 2 y un grado 1 sería defendible.

- Los dos grado 1 son coherentes y bien diferenciados del grado 2: `ca53d682` *"describe los certificados de avalúo fiscal y su emisión, pero no se enfoca en condominios específicamente"* y `00045cfe` *"reclamo contra una resolución del SII... afectando su avalúo fiscal"*. Ambos rozan el avalúo fiscal sin abordar el caso de condominios bajo la ley de copropiedad, que es exactamente la zona intermedia que define el grado 1.

En conjunto, la variabilidad observada es ruido inherente al método LLM-as-judge y de bajo impacto: ningún par equivalente recibe grados opuestos, y la frontera 2-vs-1 está razonablemente trazada.

## Ausencia del grado 3

Ningún chunk recibió grado 3, y esta ausencia merece atención por su efecto sobre las métricas.

La explicación más probable es del **corpus**, no del juez: la query pide avalúo *y reavalúo* de condominios acogidos a la ley de copropiedad, y el pool está poblado por circulares e instructivos que explican el procedimiento, los formularios y la distinción entre condominios tipo A y B. Ese material responde correctamente a "cómo se calcula el avalúo de un condominio" (grado 2), pero ningún fragmento individual responde de forma directa y exhaustiva a la pregunta completa —en particular, el componente de *reavalúo* apenas aparece de forma explícita—. No hay un chunk único que cubra el tema de lleno; el conocimiento está repartido en fragmentos parciales.

No se descarta una contribución del **juez**, que en este pool aplicó un criterio uniformemente conservador en el extremo alto (ver inconsistencias: tres chunks que "reemplazan/actualizan el procedimiento" se quedaron en grado 2). Pero aun reclasificando alguno de esos a grado 3, la query seguiría siendo poco discriminante, porque el problema de fondo es la homogeneidad del pool, no el corte del umbral.

La consecuencia es directa y debe declararse con honestidad: con cero grado 3 y umbral `grado >= 3`, **P@k vale 0 en todas las técnicas y todos los k**. La métrica de precisión queda inutilizada para esta query, y la única señal disponible es el `mean_grade`, que tampoco logra separar a casi ninguna técnica.

## Resultados de `evaluate_query.py`

La evaluación confirma el diagnóstico:

- **P@k = 0 en las 8 técnicas y en todos los k** (1, 3, 5, 10), por la ausencia total de grado 3.
- Por `top-10 mean_grade` hay un **empate de seis técnicas en 2.00**: `p1_bm25`, `p1_splade`, `p2_bm25`, `p2_tfidf`, `p3_bm25` y `p3_tfidf`. Detrás quedan `p1_tfidf` (1.90) y, muy lejos, `baseline_qdrant_bm25` (0.143).
- La ganadora nominal por `top-10 mean_grade` es `p1_bm25` (2.00), pero es un ganador puramente nominal: el desempate entre las seis técnicas líderes es inexistente.

La discriminación entre técnicas es prácticamente nula. Todas las técnicas P1/P2/P3 (salvo `p1_tfidf` por un chunk) recuperan exactamente el mismo tipo de material de grado 2 y empatan. La única separación real es respecto del baseline, que sí degrada (recupera chunks de grado 0 en su top), pero esa comparación ya está cubierta sobradamente por otras queries. La query aporta **cobertura del área de avalúo fiscal de copropiedades**, pero **no aporta señal discriminante** entre las técnicas que de verdad se quieren comparar.

## Conclusión

Los juicios de q014 son **coherentes y utilizables como ground truth de relevancia**: los extremos del pool están bien clasificados, la frontera 2-vs-1-vs-0 está razonablemente trazada, no hay parse errors ni correcciones manuales, y la única objeción —la ausencia de grado 3— se explica mejor por la homogeneidad del corpus que por un fallo del juez.

Sin embargo, como **instrumento experimental la query tiene bajo valor**: con P@k = 0 universal y seis técnicas empatadas en `mean_grade`, no separa a las técnicas de retrieval, que es el objetivo del benchmark. Según el criterio del documento guía ("es mejor terminar con 4 queries buenas que con 5 mediocres"), esta query es candidata a ser reemplazada por una más discriminante. La recomendación es conservarla únicamente si se valora su aporte de **cobertura del área de copropiedad/avalúo fiscal** —dejando constancia explícita de que no discrimina— y, en caso contrario, sustituirla por una query del mismo dominio formulada de forma más específica (por ejemplo, centrada solo en el procedimiento de reavalúo) que tenga más probabilidad de generar un chunk de grado 3 y, con él, señal en P@k.
