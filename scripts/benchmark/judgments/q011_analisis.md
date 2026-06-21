# Análisis del juicio LLM — q011

**Query**: *"IVA en el arriendo de espacios o bienes comunes de un edificio acogido a copropiedad"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-09
**Chunks evaluados**: 45

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 7 | 16% |
| 2 (relevante) | 17 | 38% |
| 1 (marginal) | 11 | 24% |
| 0 (irrelevante) | 10 | 22% |
| -1 (parse error) | 0 | 0% |

A diferencia de queries con tema muy acotado, acá aparecen los cuatro grados con masa real, lo que confirma que el juez está discriminando. La distribución no es la ideal del prompt ("20-30% grado 3, mayoría en grado 2"): el grado 3 queda algo bajo (16%) y la masa principal se concentra en los grados 1 y 2 (62% combinado). Esto es coherente con la naturaleza de la consulta: el corpus tiene muchos oficios que tratan el IVA en arriendos *en general* o la tributación de comunidades *sin enfocarse* específicamente en bienes comunes, y esos fragmentos caen naturalmente en la zona intermedia (grado 1-2) en vez de responder de lleno la pregunta. El grado 3 conservador es esperable y no preocupante: hay 7 chunks que responden directamente, suficientes para dar señal a las métricas P@k.

## Aciertos

Los grado 3 más sólidos corresponden a fragmentos que abordan de frente el IVA sobre el arriendo de espacios o bienes comunes de una copropiedad:

- `6ed06538`: *"Este oficio establece explícitamente que el cobro a copropietarios por uso de bienes comunes para estacionamiento no está gravado con IVA"*. Responde directamente al núcleo de la consulta.
- `eedd130e`: *"Este fragmento aborda directamente el IVA en el arriendo de espacios comunes de un condominio, respondiendo la consulta"*.
- `8b92f691`: *"Este oficio aborda la tributación de ingresos extras de condominios, incluyendo explícitamente el arriendo de espacios comunes y la consulta sobre IVA"*.
- `dd685307`: *"Este oficio aborda la tributación de una comunidad de edificio por arriendo de espacios comunes para antenas, siendo altamente relevante"*.

Los grado 0 también están bien clasificados: son fragmentos del dominio de copropiedad pero ajenos al IVA en arriendos. Por ejemplo `6a19e616` (*"aborda la exención de impuesto territorial para copropiedades, no el IVA en arriendos de bienes comunes"*) y `89c733d4` (*"se enfoca en la tasación de bienes comunes y unidades, no en el IVA de arriendos"*). El juez distingue correctamente "copropiedad + tributación territorial/avalúo" de "copropiedad + IVA en arriendos", que es la trampa léxica de esta query.

## Inconsistencias detectadas

No se observan errores objetivos graves (alucinaciones del juez ni grados claramente disparatados). El ruido se concentra, como es habitual, en la frontera entre grado 2 y grado 3:

- `69c0f911` (grado 3): *"aborda el IVA en el arriendo de espacios comunes, indicando que si la comunidad desarrolla esta actividad, los ingresos son gravados"*.
- `579d2396` (grado 2): *"indica que si una comunidad arrienda espacios comunes, puede ser contribuyente de Primera Categoría y estar afecta a impuestos"*.

Ambas justificaciones describen el mismo escenario (comunidad que arrienda espacios comunes y queda gravada), pero el primero recibió grado 3 y el segundo grado 2. La diferencia plausible es que `579d2396` habla de Primera Categoría más que de IVA puntual, pero la frontera es fina.

Un caso algo generoso es `b5f8a8a6` (grado 3): *"analiza la aplicación del IVA al arriendo de locales comerciales, incluyendo el acceso a instalaciones comunes"*. El foco está en locales comerciales y las instalaciones comunes aparecen como accesorio; una clasificación de grado 2 sería defendible, en línea con `9c8bd8e8` (grado 2, *"analiza el IVA en arrendamiento de inmuebles dentro de un complejo, incluyendo instalaciones, pero no se enfoca en bienes comunes de copropiedad"*), cuya justificación es muy similar. Por tratarse de un único caso de frontera sobre 45, el impacto sobre las métricas agregadas es marginal.

## Balance entre grados

A diferencia de queries de dominio acotado donde algún grado intermedio desaparece, acá están presentes los cuatro grados (3/2/1/0) con cantidades sustantivas y sin ningún `relevance_grade: -1`. El grado 1 es notoriamente poblado (11 chunks, 24%), lo cual es propio de esta consulta: existe una zona amplia de fragmentos "tangencialmente relacionados" —arriendos con opción de compra, avalúos de bienes comunes, determinación de derechos en copropiedad— que comparten vocabulario con la query pero no tratan el IVA sobre el arriendo de bienes comunes. El juez los ubica correctamente en grado 1 en vez de inflarlos a 2 o degradarlos a 0, lo que habla bien de su calibración para esta query.

## Resultados de `evaluate_query.py`

La técnica ganadora por `top-10 mean_grade` es **`p1_splade` (2.40)**, empatada con **`p3_bm25` (2.40)**. El rango de la métrica es amplio: va de 0.40 en `baseline_qdrant_bm25` hasta 2.40 en las punteras, de modo que la query discrimina con fuerza entre técnicas y aporta señal experimental clara.

El resultado coincide con la intuición. Es una consulta tributaria con vocabulario técnico ("IVA", "arriendo", "espacios/bienes comunes", "copropiedad") que SPLADE expande bien semánticamente, capturando oficios que usan términos equivalentes (condominio, comunidad, instalaciones comunes) sin coincidencia léxica exacta. El empate con `p3_bm25` muestra que, una vez normalizado el texto, el match léxico fuerte también alcanza buen desempeño en esta query. El derrumbe del `baseline_qdrant_bm25` (0.40) confirma que la pipeline esparsa del proyecto supera ampliamente al baseline para esta consulta.

## Conclusión

Los juicios son utilizables como ground truth para esta query. Aparecen los cuatro grados con masa razonable, no hay parse errors ni correcciones manuales, los extremos del pool (grado 3 y grado 0) están correctamente clasificados, y el único ruido relevante está en la frontera 2-vs-3, dentro del rango esperado para un juez LLM single-pass. El grado 3 algo conservador (16%) no compromete el ground truth: hay 7 chunks altamente relevantes, suficientes para alimentar las métricas P@k y diferenciar técnicas. La query queda validada y se procede a la evaluación con `evaluate_query.py`.
