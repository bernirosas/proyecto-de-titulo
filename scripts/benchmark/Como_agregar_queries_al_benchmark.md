# Cómo aportar queries al benchmark

Esta guía es para los integrantes del grupo que vayan a curar consultas de evaluación. **Cada persona aporta 5 queries** del dominio inmobiliario chileno. Con 4 personas llegamos a 20 queries totales, que es el rango típico para un conjunto de evaluación de retrieval defendible en una tesis.

## Por qué importa esta tarea

El benchmark final compara las 7 técnicas esparsas usando métricas (Recall@k, MRR, NDCG) calculadas contra el grado de relevancia que Gemini asigna a cada chunk. Esas métricas solo tienen sentido si las queries son representativas de lo que el chatbot de Maqui debería resolver en producción. Una query mal curada (demasiado vaga, demasiado específica, fuera de dominio) contamina las métricas y oculta diferencias reales entre técnicas.

## Qué hace una buena query

**Una buena query inmobiliaria cumple cuatro criterios:**

1. **Es algo que un usuario real preguntaría a Maqui.ai.** No "el contrato del Código Civil chileno", sino "¿en qué casos puede el arrendador desahuciar al arrendatario?". Pensar en un asesor que llega con dudas concretas.

2. **Tiene respuesta en el corpus.** El corpus son chunks de oficios SII, circulares, resoluciones, jurisprudencia y leyes BCN. Si la consulta es sobre normativa internacional o sobre algo que el cliente jamás cargó, ningún chunk va a ser relevante y la query no aporta.

3. **No es ni demasiado general ni demasiado específica.**
   - Demasiado general: "arrendamiento" → todo el corpus es marginalmente relevante, no discrimina entre técnicas.
   - Demasiado específica: "Resolución exenta SII N° 199 de 2023" → un único chunk responde, no hay margen para comparar técnicas.
   - Sweet spot: una pregunta concreta sobre un concepto o procedimiento, con 3—10 chunks claramente relevantes.

4. **Es ambigua entre técnicas.** Si todas las técnicas devuelven los mismos chunks, la query no aporta señal experimental. Las queries más útiles son aquellas donde **BM25 tradicional y SPLADE** podrían devolver cosas distintas (porque BM25 hace match léxico exacto, mientras SPLADE expande semánticamente con WordPieces).

## Áreas a cubrir (para que las 20 queries sean diversas)

Cada persona elige **5 queries cubriendo al menos 3 de estas 6 áreas**:

| Área | Ejemplo de query |
|---|---|
| Arrendamiento de inmuebles | "Obligaciones del arrendatario al término del contrato" | Carli
| Compraventa de bienes raíces | "Requisitos de la escritura pública en una compraventa" | Tomás
| Copropiedad / propiedad horizontal | "Quórum para modificar el reglamento de copropiedad" | Pablo
| Tributación inmobiliaria | "Devolución del IVA en venta de inmuebles" | Dussan
| Recursos sobre bienes raíces | "Recurso de protección sobre el derecho de propiedad" | Martín
| Jurisprudencia sobre inmuebles | "Doctrina sobre cumplimiento defectuoso en compraventa" | Berni

## Formato de archivo

Cada query es un archivo JSON en `scripts/benchmark/queries/`. **El nombre del archivo sigue la convención**:

```
q{NNN}_{slug_corto_descriptivo}.json
```

Donde `NNN` es un número de tres dígitos correlativo y el slug describe brevemente la query en minúsculas, sin acentos, separado por guiones bajos.

Ejemplos válidos:

- `q002_desahucio_arrendatario.json`
- `q003_quorum_copropiedad.json`
- `q004_iva_venta_inmuebles.json`

**Coordinen los números** para no chocar. Sugerencia: persona A toma 002—006, persona B 007—011, persona C 012—016, persona D 017—021.

### Contenido del JSON

El schema es deliberadamente mínimo: el MER del benchmark solo requiere identificador y texto de la consulta. Todo lo demás (área, dificultad, observaciones del juez) va al campo libre `notas`, que se completa al final del flujo cuando ya se vio cómo respondieron las técnicas.

```json
{
  "query_id": "q002",
  "query_text": "¿En qué casos puede el arrendador desahuciar al arrendatario antes del término del contrato?",
  "notas": "Cubre arrendamiento. p1_splade trae los chunks de jurisprudencia que p1_bm25 no encuentra. Ganadora top-10 mean_grade: p1_splade (2.31)."
}
```

**Campos:**

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `query_id` | string | Sí | Mismo identificador del nombre del archivo (`q002`). |
| `query_text` | string | Sí | La consulta real, escrita como la formularía un usuario. |
| `notas` | string | No | Anotación libre que se completa al final del flujo: área cubierta, observaciones sobre discriminación entre técnicas, técnica ganadora según `evaluate_query.py`, correcciones manuales sobre el juicio del LLM. |

## Flujo completo para validar su aporte (paso a paso)

Asumimos que ya tiene los servicios levantados (`docker compose up -d`). Para cada query que cure:

### 1. Crear el archivo JSON

Edite o cree el archivo en `scripts/benchmark/queries/qNNN_slug.json` siguiendo el formato de arriba.

### 2. Probar la query en el frontend antes de comprometerse

Abra `http://localhost:8000/` y pegue su `query_text` en el buscador. Pruebe **al menos 3 técnicas distintas** (p. ej. `p1_bm25`, `p3_bm25`, `p1_splade`). Observe:

- ¿Cada técnica devuelve al menos algunos chunks?
- ¿Los chunks devueltos parecen relevantes a ojo?
- ¿Las técnicas difieren entre sí (rankings distintos)?

Si en las tres técnicas devuelve la misma lista, o si ninguna devuelve hits útiles, la query no sirve — cambie el texto y vuelva a probar.

### 3. Ejecutar el retrieval para que se ingese en OpenSearch

```bash
docker compose run --rm app \
    python scripts/benchmark/retrieve_for_query.py \
        --query-file scripts/benchmark/queries/qNNN_slug.json \
        --output-dir scripts/benchmark/pools \
        --size 10
```

Mire el log: el "Pool sin repeticiones" debe estar entre 25 y 60 chunks únicos. Si es mucho menos (10—15) o mucho más (cerca de 70), revise la query — es señal de que es demasiado restrictiva o demasiado general.

### 4. Juzgar los chunks con Gemini

```bash
export GEMINI_API_KEY="..."  # solo una vez por sesión
docker compose run --rm \
    -e GEMINI_API_KEY \
    app python scripts/benchmark/judge_pool.py \
        --pool-file scripts/benchmark/pools/qNNN.json \
        --output-dir scripts/benchmark/judgments \
        --model gemini-2.5-flash-lite
```

**Sobre el modelo:** desde junio 2026 Google deshabilitó el free tier de `gemini-2.0-flash` (la cuota es `limit: 0`). El default del script sigue siendo ese modelo histórico, así que **siempre pase `--model gemini-2.5-flash-lite` explícitamente** mientras no actualicemos el default. Ese modelo tiene 15 RPM y 1000 RPD en capa gratis, lo cual permite juzgar unas 25 queries diarias sin pagar.

**Sobre el tiempo:** el script juzga en *batches* de 5 chunks por llamada al LLM. Para un pool típico de ~36 chunks → 8 batches × ~5 segundos = aproximadamente 40-60 segundos por query (mucho menos que cuando era un chunk por llamada).

**Si ve `ABORTANDO: Google deshabilitó el FREE TIER`:** está corriendo con el default viejo (`gemini-2.0-flash`). Reintente con la flag `--model gemini-2.5-flash-lite`.

**Si ve `ABORTANDO: cuota DIARIA agotada`:** la cuota se resetea a medianoche UTC (20:00 hora Chile en invierno). Espere o use otra API key.

### 5. Juzgar y analizar los resultados de la query

Esta es la parte más importante de su aporte: el LLM hace una primera pasada automática, pero **cada integrante debe validar críticamente los judgments** y analizar qué dicen los resultados sobre las técnicas. Sin esto, una alucinación del LLM o un sesgo sistemático queda enterrado en las métricas finales.

#### 5.1. Validar el juicio del LLM

Abra `scripts/benchmark/judgments/qNNN_judgments.json` y revise los siguientes puntos en orden:

**Chequeos rápidos primero:**

- **Distribución sana de grados**: ojalá tenga al menos un 3, varios 2, varios 1 y algunos 0. Si todos los chunks recibieron el mismo grado, el LLM no está discriminando — probablemente su query es demasiado vaga o demasiado específica.
- **Cero `relevance_grade: -1`**: estos son fallas de parseo de Gemini. Si encuentra alguno, anótelo en sus notas y avise al equipo (probablemente un edge case del prompt).
- **Cantidad razonable de relevantes (grados 2 y 3)**: típicamente entre 5 y 15 sobre 36 chunks. Si hay menos de 3 relevantes, la query no aporta señal experimental porque las métricas Recall@k se basan justamente en cuántos relevantes recupera cada técnica.

**Validación cualitativa (la más valiosa):**

Tome muestras de **al menos 5 chunks por grado** y compárelos con su `justification`. Para cada uno, hágase tres preguntas:

1. ¿La `justification` es coherente con el contenido del chunk? Si la justificación dice "aborda la prescripción de cobro" pero el chunk habla de algo totalmente distinto, el LLM alucinó.
2. ¿El grado parece justo para ese contenido? Si un chunk responde directa y exhaustivamente la consulta pero recibió un 2, el LLM fue demasiado estricto. Si un chunk tangencial recibió un 3, fue demasiado generoso.
3. ¿La distinción 2 vs 3 está bien aplicada? La diferencia entre "relevante" y "altamente relevante" suele ser la frontera más sutil. Revise específicamente esos casos.

**Cuándo sobreescribir el juicio del LLM:**

Si encuentra **3 o más errores claros** (no diferencias de opinión, sino errores objetivos como "este chunk no tiene nada que ver y recibió un 3"), edite el archivo `qNNN_judgments.json` a mano, corrigiendo los grados que crea necesarios y **agregando al final de la `justification` la nota `[corregido manualmente: motivo]`** para dejar trazabilidad. Por ejemplo:

```json
{
  "chunk_uuid": "abc-123",
  "relevance_grade": 1,
  "justification": "Aborda materia tributaria general pero no la consulta específica. [corregido manualmente: el LLM puso 3 pero el chunk no menciona arrendamiento]"
}
```

Si encuentra **muchos errores** (digamos más del 20% del pool), avise al equipo: probablemente hay que ajustar el prompt del juez o la query es ambigua.

#### 5.2. Computar las métricas formales con `evaluate_query.py`

Antes de mirar los rankings a ojo, deje que el script saque las cuentas:

```bash
docker compose run --rm app \
    python scripts/benchmark/evaluate_query.py \
        --pool-file scripts/benchmark/pools/qNNN.json \
        --judgments-file scripts/benchmark/judgments/qNNN_judgments.json \
        --output-file scripts/benchmark/evaluations/qNNN_eval.json
```

Esto imprime una tabla con dos métricas por técnica y por cada k ∈ {1, 3, 5, 10}:

- **`mean_grade`**: promedio de los grados (0-3) que el juez asignó a los primeros k chunks de cada técnica. Mayor es mejor.
- **`P@k`**: fracción de los primeros k chunks que el juez consideró **altamente relevantes** (grado 3, criterio estricto). P@5 = 0.8 significa "4 de los 5 primeros chunks contienen la respuesta principal".

Al final del output el script identifica **la técnica ganadora por `top-10 mean_grade`**. Anote ese nombre — será un input para su análisis cualitativo más abajo.

El script genera automáticamente dos archivos en `scripts/benchmark/evaluations/`:

- `qNNN_eval.json`: las métricas crudas para procesamiento posterior.
- `qNNN_eval.txt`: la misma tabla legible que ve en stdout, lista para citar en su archivo de análisis sin tener que copiar de la terminal.

#### 5.3. Analizar las diferencias entre técnicas

Ahora que tiene las métricas formales, abra `scripts/benchmark/pools/qNNN.json` (rankings originales por técnica) junto con `qNNN_judgments.json` para responder: **¿qué técnica funcionó mejor y por qué?**

Mire los siguientes puntos:

**a) ¿Cuál técnica devolvió más chunks de grado 3 en el top-5?**

Recorra los `rankings` de cada técnica, mire los primeros 5 chunks, y para cada uno busque su grado en los judgments. Anote, por técnica:

- Cantidad de chunks de grado 3 en el top-5.
- Cantidad de chunks de grado 0 (irrelevantes) que se colaron al top-5.

Las técnicas con pocos grado 3 al inicio o muchos grado 0 al inicio son las que peor rankearon esta query.

**b) ¿Dónde hay desacuerdos interesantes entre técnicas?**

Identifique al menos un chunk que cumpla **una de estas condiciones**:

- Aparece en el top-3 de una técnica pero **no aparece en el top-10 de otra**. Si es de grado 3, la técnica que lo encontró está capturando algo que las otras no — anote cuál fue (probablemente SPLADE si el match es semántico, o BM25 si es léxico exacto).
- Aparece en el top-3 de varias técnicas pero recibió grado 0 o 1. Las técnicas coinciden en algo que el LLM marcó como irrelevante — vale la pena entender por qué (¿el chunk usa el mismo vocabulario que la query pero habla de otro tema?).

**c) ¿La query discrimina técnicas o todas son equivalentes?**

Si las 7 técnicas devuelven aproximadamente los mismos top-10 (con orden distinto pero set similar), la query no aporta señal experimental fuerte. Anótelo en su archivo de query, campo `notas`: `"baja discriminación entre técnicas — chunks muy convergentes"`.

Si en cambio las técnicas devuelven listas claramente distintas, la query es valiosa para el experimento. Anote en `notas` qué eje las separa: `"BM25 favorece <X>; SPLADE favorece <Y>"`.

#### 5.4. Escribir el archivo de análisis `qNNN_analisis.md`

Guarde junto a los judgments un archivo markdown con el análisis de su query, en `scripts/benchmark/judgments/qNNN_analisis.md`. Este archivo es el deliverable cualitativo de su aporte y queda en el repo como evidencia para la tesis.

Use como plantilla el análisis de q001 (`scripts/benchmark/judgments/q001_analisis.md`) y cubra estas secciones:

1. **Metadata**: query, modelo del juez, fecha, número de chunks evaluados.
2. **Distribución de grados**: tabla con grados 0-3 y -1 (parse errors), conteos y porcentajes. Si la distribución es muy distinta de "20-30% grado 3, mayoría en grado 2", explique por qué.
3. **Aciertos**: dé 2-4 ejemplos concretos de chunks bien clasificados (cite el `chunk_uuid` corto y la justificación).
4. **Inconsistencias detectadas**: pares de chunks con justificaciones equivalentes pero grados distintos, casos cuestionables (p. ej. un grado 3 que debería ser 2). Esto es lo más valioso de su análisis porque muestra los límites del juez LLM.
5. **Ausencia de algún grado**: si grado 1 (o grado 0) no aparece, explique si es esperable para esta query o si delata un sesgo del prompt.
6. **Resultados de `evaluate_query.py`**: cite la técnica ganadora por `top-10 mean_grade` y comente brevemente si coincide con su intuición del paso 5.3.
7. **Conclusión**: indique si los juicios son utilizables como ground truth para esta query o si encontró problemas que ameritan revisar el prompt / la query.

#### 5.5. Qué anotar en sus notas finales

Cuando declare sus 5 queries listas, complete o expanda el campo `notas` del JSON de cada query (`scripts/benchmark/queries/qNNN_*.json`) cubriendo tres puntos:

1. Si tuvo que corregir manualmente algún judgment (cuántos y por qué).
2. Si la query discrimina bien entre técnicas o no.
3. Qué técnica resultó ganadora según `evaluate_query.py` (`top-10 mean_grade`).

Ejemplo de un campo `notas` completo:

```json
"notas": "Cruza jurisprudencia y oficios SII. Discrimina bien: p1_splade trae los chunks de jurisprudencia que p1_bm25 no encuentra (vocabulario distinto). Ganadora top-10 mean_grade: p1_splade (2.31). 2 judgments corregidos manualmente: chunks 5b7e... y 8c1a... el LLM les puso 3 pero hablan de prescripción civil, no tributaria."
```

Esa información va a servir al momento de redactar la sección de resultados de la tesis y de defender frente al cliente por qué se eligieron ciertas técnicas como ganadoras.

#### 5.6. Cuándo volver al paso 3

Tras los chequeos anteriores, si concluye que **la query no sirve** (distribución plana, todos los grados iguales, o el LLM falló sistemáticamente), descarte la query y elija otra del listado de áreas. Es mejor terminar con 4 queries buenas que con 5 mediocres.

Si la query sí sirve pero quiere afinarla (por ejemplo, hacerla más específica o más amplia), ajuste el `query_text` en `scripts/benchmark/queries/qNNN_*.json` y vuelva al paso 3 — los archivos antiguos en `pools/` y `judgments/` se sobrescriben automáticamente.

### 6. Ingestar todos los judgments al final

Cuando las 20 queries estén juzgadas, alguien del equipo corre una sola vez:

```bash
docker compose run --rm app \
    python scripts/benchmark/ingest_judgments.py \
        --judgments-dir scripts/benchmark/judgments \
        --summary-file scripts/benchmark/summary.json
```

Esto consolida todos los judgments en el índice `ground_truth` de OpenSearch y genera un resumen.

## Checklist antes de declarar listas sus 5 queries

**Curación de la query:**

- [ ] Cada query cubre un área distinta de las 6 listadas (al menos 3 áreas en total).
- [ ] Ninguna query duplica un `query_id` ya tomado por otro integrante.
- [ ] Cada `qNNN.json` se validó en el frontend con al menos 3 técnicas.
- [ ] Cada `pools/qNNN.json` tiene entre 25 y 60 chunks únicos.

**Validación del juicio LLM (paso 5.1):**

- [ ] Distribución de grados sana (no todos iguales; al menos 3 chunks ≥ 2).
- [ ] Cero `relevance_grade: -1` (o reportado al equipo).
- [ ] Revisó al menos 5 chunks de cada grado verificando que la `justification` sea coherente.
- [ ] Documentó cualquier corrección manual con la nota `[corregido manualmente: motivo]`.

**Métricas formales (paso 5.2):**

- [ ] Corrió `evaluate_query.py` y guardó el output en `scripts/benchmark/evaluations/qNNN_eval.json`.
- [ ] Anotó la técnica ganadora por `top-10 mean_grade`.

**Análisis comparativo entre técnicas (paso 5.3):**

- [ ] Identificó qué técnica devolvió más chunks de grado 3 en el top-5.
- [ ] Anotó al menos un caso de desacuerdo interesante entre técnicas.
- [ ] Determinó si la query discrimina bien o no.

**Archivo de análisis (paso 5.4):**

- [ ] Escribió `scripts/benchmark/judgments/qNNN_analisis.md` siguiendo la plantilla de q001 (distribución, aciertos, inconsistencias, conclusión).

**Notas finales (paso 5.5):**

- [ ] Campo `notas` del JSON original incluye: área cubierta, observaciones sobre discriminación, correcciones manuales hechas, y técnica ganadora según `evaluate_query.py`.

## Consejos prácticos

- **Si Gemini falla con error de API key**: probablemente exportó `GEMINI_API_KEY` en una terminal y está corriendo Docker desde otra. El `-e GEMINI_API_KEY` en el `docker compose run` toma el valor de la terminal actual.
- **Si el script tarda mucho más de 60 segundos por query**: revise si la query produjo un pool de más de 60 chunks. Con batches de 5, cada query son ~8 llamadas al LLM de ~5s cada una.
- **Si recibe `ABORTANDO: cuota DIARIA agotada`**: espere al reset (medianoche UTC, 20:00 hora Chile en invierno) o use otra API key.
- **Si recibe `ABORTANDO: Google deshabilitó el FREE TIER`**: olvidó la flag `--model gemini-2.5-flash-lite`. Vuelva a correr con esa flag.
- **Si una query no le convence después de ver los grados**: archívela. Mejor 4 queries buenas que 5 mediocres.
- **Comparta queries entre ustedes antes de finalizarlas**: si dos integrantes curan queries muy parecidas, las métricas finales pierden diversidad.

## Preguntas frecuentes

**¿Puedo usar acentos en `query_text`?** Sí. Los preprocesadores P2 y P3 los normalizan; P1 los conserva. Escriba en español natural.

**¿La query debe terminar en signo de interrogación?** Indistinto. El tokenizador trata los signos como puntuación que se filtra; lo que importa es el contenido.

**¿Qué pasa si una query no devuelve ningún hit en alguna técnica?** Se documenta como Recall@k = 0 para esa técnica en esa query, sin interrumpir el resto. Es información válida — significa que esa técnica fracasó completamente, lo cual es un dato del experimento.

**¿Puedo proponer queries que sé que rompen a alguna técnica específica?** Sí, son las más valiosas. Una query con vocabulario poco común que BM25 no encuentra pero SPLADE sí, o viceversa, es exactamente lo que diferencia las técnicas y le da contenido a la tesis.
