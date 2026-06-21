# Análisis del juicio LLM — q018

**Query**: *"¿Cómo tributa el mayor valor obtenido en la venta de un bien raíz adquirido después del año 2004?"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-11
**Chunks evaluados**: 33 (2 corregidos manualmente por parse error)

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 7 | 21% |
| 2 (relevante) | 19 | 58% |
| 1 (marginal) | 5 | 15% |
| 0 (irrelevante) | 2 | 6% |
| -1 (parse error) | 0 | 0% |

Distribución dominada por grado 2 (58%), con pocos grado 3 (21%). El pool es el más pequeño de las 5 queries (33 chunks), señal de que "mayor valor" + "bien raíz" + "después de 2004" es una combinación léxica suficientemente específica como para no traer chunks dispersos, pero la restricción temporal (post-2004) hace que muchos chunks relevantes que tratan el régimen pre-2004 caigan en grado 2 o 1.

## Aciertos

Los grado 3 correctamente identificados:

- `ebb775f1` (Oficio N°330/2022): explica la tributación del mayor valor en bienes raíces bajo la ley vigente hasta 2014, diferenciando el régimen pre y post 2004.
- `925811d4` y `dfb97857`: indican que el mayor valor en venta de bien raíz adquirido antes de 2004 es ingreso no renta — chunks que el juez correctamente marcó como grado 3 por ser los que definen el límite temporal de la query.

Los grado 0 son correctos: un fragmento sobre tributación de mayor valor en venta de *acciones* (`049dc1c4`) y otro sobre depreciación acelerada y presunciones de retiro (`42ee0795`) son completamente ajenos.

## Inconsistencias detectadas

El juez aplicó un criterio estricto: chunks que tratan el régimen de *bienes adquiridos antes de 2004* recibieron sistemáticamente grado 1, aunque esos chunks son el contrapunto necesario para entender el régimen post-2004. Ejemplos:

- `8a7e5759` (grado 1): justificación "aborda bienes raíces adquiridos antes de 2004, pero la consulta es sobre después de 2004". El chunk efectivamente define el límite temporal por contraste, lo que lo hace relevante.
- `ddfd11d8` y `36cd6484` (grado 1): mismo patrón.

Esta distinción es técnicamente defendible (la query pregunta por el régimen post-2004), pero en la práctica un usuario que recibe esos chunks obtiene información valiosa de contexto. Una clasificación de grado 2 sería igualmente razonable. No se corrigieron manualmente por ser consistentes entre sí.

## Correcciones manuales

Se corrigieron 2 chunks con parse error (-1):

- `3017d408` (Oficio N°3102/2016): corregido a **grado 3**. El oficio trata directamente la tributación en enajenación de bienes raíces post-reforma 2014.
- `27fc274a` (Oficio N°3633/2022): corregido a **grado 3**. Cita Art. 17 N°8 LIR y Ley 20.780, el núcleo normativo de la tributación del mayor valor post-2004.

## Resultados de evaluate_query.py

| Técnica | top-10 mean | top-10 P@k |
|---------|------------:|-----------:|
| **p1_splade** | **2.500** | **0.500** |
| p2_bm25 | 2.200 | 0.400 |
| p1_bm25 | 2.100 | 0.300 |
| p2_tfidf | 2.100 | 0.300 |
| p3_tfidf | 2.100 | 0.300 |
| p3_bm25 | 1.900 | 0.100 |
| p1_tfidf | 1.900 | 0.300 |
| baseline_qdrant_bm25 | 1.600 | 0.200 |

**Técnica ganadora**: `p1_splade` (2.500). Es la única query de las 5 donde SPLADE supera a BM25. El top-5 de p1_splade es `[2,2,2,3,3]` — consistente aunque sin arranque fuerte. El top-5 de p1_bm25 es `[3,1,2,3,2]` — arranque fuerte pero con un grado 1 en segunda posición que penaliza las métricas. La hipótesis es que SPLADE expande "mayor valor" hacia "enajenación", "plusvalía" y "Art. 17 N°8", capturando chunks que BM25 no encuentra por match léxico exacto.

## Conclusión

Los juicios son utilizables como ground truth. El pool pequeño (33 chunks) y la dominancia del grado 2 son esperables para una query con restricción temporal precisa. La victoria de SPLADE es el dato más interesante de esta query y la hace valiosa para la tesis: es evidencia de que la expansión semántica ayuda cuando la terminología legal es más formal y técnica que el vocabulario de la consulta.
