# Análisis del juicio LLM — q000

**Query**: *"Plazo de prescripción para el cobro de impuestos"*
**Modelo juez**: `gemini-2.5-flash-lite`
**Fecha del juicio**: 2026-06-01
**Chunks evaluados**: 36

## Distribución de grados

| Grado | Cantidad | Porcentaje |
|-------|---------:|-----------:|
| 3 (altamente relevante) | 11 | 31% |
| 2 (relevante) | 23 | 64% |
| 1 (marginal) | 0 | 0% |
| 0 (irrelevante) | 2 | 6% |
| -1 (parse error) | 0 | 0% |

La distribución está en el rango objetivo definido en el prompt ("no más del 20-30% debería ser grado 3"). Esto contrasta con una corrida previa que arrojó 86% de grado 3 antes de ajustar el prompt para hacer más restrictivo el grado más alto.

## Aciertos

Los dos chunks con grado 0 son clasificaciones correctas: un fragmento del Código de Comercio sobre contratos marítimos y otro sobre la modificación de un formulario administrativo. Ninguno guarda relación con plazos de prescripción tributaria.

Los grado 3 más fuertes corresponden a fragmentos que efectivamente detallan los plazos de tres y seis años establecidos en el artículo 200 del Código Tributario:

- `0b70fb51`: detalla los plazos de prescripción para la acción del Fisco para cobrar impuestos, intereses y sanciones.
- `2ef643c1`: define el plazo de prescripción para el cobro de impuestos mencionando los plazos de tres o seis años.
- `7cdb5d22`: detalla la regla general de prescripción de tres años para la facultad del SII de liquidar y girar impuestos.
- `d41bf71b`: define el plazo de prescripción del Fisco para el cobro de impuestos, intereses y sanciones.

## Inconsistencias detectadas

Se observan pares de chunks con justificaciones casi equivalentes que reciben grados distintos:

- `2ef643c1` (grado 3): *"define el plazo de prescripción para el cobro de impuestos, mencionando los plazos de tres o seis años"*.
- `cb7e0599` (grado 2): *"explica los plazos de prescripción de tres y seis años para liquidar y girar impuestos"*.

El mismo patrón aparece entre `7cdb5d22` (grado 3) y `3da51d94` (grado 2). Esta variabilidad es ruido inherente al método LLM-as-judge, no un defecto del pipeline. Para mitigarlo se recomienda, en trabajo futuro, medir agreement entre dos corridas independientes o entre dos jueces distintos.

Caso aislado cuestionable: `471996cf` recibió grado 3 con la justificación *"explica que la prescripción extintiva libera al Fisco de la acción de cobro"*. Esa explicación corresponde a doctrina general más que a la información puntual del plazo solicitado. Una clasificación de grado 2 sería más adecuada. Por tratarse de un único caso sobre 36, el impacto sobre las métricas agregadas es marginal.

## Ausencia del grado 1

Ningún chunk recibió grado 1. Este resultado es esperable para una consulta con tema acotado: los fragmentos del corpus o pertenecen al dominio tributario (y por lo tanto alcanzan al menos grado 2) o son completamente ajenos (grado 0). No existe en este pool una zona intermedia de chunks "tangencialmente relacionados". Si el patrón se repite en queries futuras de dominios distintos, convendrá revisar la definición del grado 1 en el prompt.

## Conclusión

Los juicios son utilizables como ground truth para esta query. La distribución cumple el criterio de conservadurismo definido en el prompt, los extremos del pool están correctamente clasificados, y el ruido observado en la frontera entre grado 2 y grado 3 está dentro del rango esperado para un juez LLM single-pass.

Se procede a la evaluación de las técnicas de retrieval con `evaluate_query.py`.
