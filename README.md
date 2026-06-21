# sparse_eval — Maqui

Backend para evaluar técnicas de recuperación esparsa (BM25, TF-IDF, SPLADE) sobre el corpus de documentos legales chilenos. El cliente puede cambiar la **técnica de vectorización** y el **preprocesamiento** desde el frontend, y la consulta se preprocesa con la misma función que se usó al indexar el corpus, garantizando comparabilidad.

Esta versión cubre los siguientes hitos del plan:

1. Levantar el motor de búsqueda (OpenSearch + Qdrant) mediante `docker compose`.
2. Ingestar 61.842 chunks combinando metadata de Qdrant con vectores precomputados de la carpeta `vectors/`.
3. Exponer un endpoint FastAPI con 7 técnicas (BM25 y TF-IDF en P1/P2/P3 + SPLADE en P1).
4. Frontend mínimo para probar y comparar.

Fuera de alcance: BGEM3, conjunto de consultas de evaluación, ground truth y harness de benchmark.

## Requisitos

- Docker Engine 24+ y Docker Compose v2.
- Snapshot de Qdrant con la colección `maqui` ya cargada en `../qdrant_storage`.
- Carpeta `vectors/` con los 7 archivos generados por el pipeline de vectorización (ver "Estructura de `vectors/`" más abajo).

Todo se ejecuta dentro de contenedores. Los preprocesadores de Python (spaCy, NLTK Snowball) se instalan dentro de la imagen Docker. El modelo `es_core_news_lg` (~560 MB) se descarga al ejecutar `build`.

## Puesta en marcha (primera vez)

```bash
# Desde 2026-1-DS-S1-Grupo10-Backend/

# 1. Verificar que la carpeta vectors/ tenga los 7 archivos esperados.
ls vectors/
#   c01_p1_tfidf.json
#   c02_p1_bm25_tokens.json
#   c03_p2_tfidf.json
#   c04_p2_bm25_tokens.json
#   c05_p3_tfidf.json
#   c06_p3_bm25_tokens.json
#   c07_p1_splade.json

# 2. Levantar servicios (OpenSearch + Dashboards + Qdrant).
docker compose up -d

# Verificar que OpenSearch esté en estado healthy.
docker compose ps
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# 3. Construir la imagen del servicio app (descarga spaCy y NLTK; demora varios minutos).
docker compose build app

# 4. Crear el índice chunks_maqui.
docker compose run --rm app python scripts/create_index.py --force

# 5. Ingestar por pases (uno por archivo).
#    Cada pase carga UN archivo (~250-400 MB de peak) y ejecuta updates parciales.
#    Total: ~15-25 min, peak de RAM ~500 MB.
docker compose run --rm app python scripts/ingest_with_vectors.py --pass all

# Si se desea ejecutar los pases por separado (útil si alguno se interrumpió):
docker compose run --rm app python scripts/ingest_with_vectors.py --pass metadata
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_bm25
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p2_bm25
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p2_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p3_bm25
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p3_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_splade

# Comprobación: deben ser ~61.842 chunks.
curl -s "http://localhost:9200/chunks_maqui/_count" | python3 -m json.tool

# 6. Levantar la API + frontend.
docker compose run --rm --service-ports app \
    uvicorn scripts.api:app --host 0.0.0.0 --port 8000

# Abrir http://localhost:8000/ en el navegador.
```

## Cómo actualizar todo después de cambios

### Si cambió el código Python (`src/`, `scripts/`)

No es necesario reconstruir la imagen: el código se monta como volumen, basta con volver a ejecutar el comando.

```bash
docker compose run --rm --service-ports app uvicorn scripts.api:app --host 0.0.0.0 --port 8000
```

### Si cambió `requirements.txt` o el Dockerfile

Es necesario reconstruir la imagen.

```bash
docker compose build app
```

### Si cambiaron los preprocesadores en `Vectorizacion/sparse-benchmark/src/preprocessors.py`

Se montan como volumen read-only, por lo que el cambio se refleja al reiniciar la API. **Importante:** si cambia la lógica de preprocesamiento, los vectores en `vectors/` quedan desactualizados; corresponde volver a ejecutar el pipeline de vectorización y reingresarlos (paso 4 + 5 del flujo anterior).

### Si cambió el schema (`src/schema.py`)

Es necesario borrar y recrear el índice, ya que OpenSearch no permite modificar mappings de campos existentes.

```bash
# 1. Borrar y recrear (--force confirma el drop).
docker compose run --rm app python scripts/create_index.py --force

# 2. Reingresar los datos.
docker compose run --rm app python scripts/ingest_with_vectors.py --pass all
```

### Si llegaron archivos nuevos a `vectors/`

Si los archivos nuevos cubren el mismo conjunto de chunks, basta con volver a ejecutar el pase correspondiente (`doc_as_upsert: true`, sobrescribe por `chunk_uuid`):

```bash
# Caso "solo cambió el TF-IDF de P2":
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p2_tfidf

# Caso "mismos chunks, todos los vectores actualizados":
docker compose run --rm app python scripts/ingest_with_vectors.py --pass all

# Caso "vectores nuevos con schema nuevo (por ejemplo, agregar P4 o BGEM3)":
# (1) editar src/schema.py para agregar los campos.
# (2) editar src/config.py: VECTOR_FILES + TECHNIQUES.
# (3) editar scripts/ingest_with_vectors.py si se requiere un pase específico.
docker compose run --rm app python scripts/create_index.py --force
docker compose run --rm app python scripts/ingest_with_vectors.py --pass all
```

### Si solo se desea volver a levantar la API sin modificar nada más

```bash
# Foreground (con logs visibles).
docker compose run --rm --service-ports app \
    uvicorn scripts.api:app --host 0.0.0.0 --port 8000

# Background.
docker compose run -d --service-ports app \
    uvicorn scripts.api:app --host 0.0.0.0 --port 8000
```

### Reset completo

```bash
# Borra el índice y vuelve a poblarlo.
docker compose run --rm app python scripts/create_index.py --force
docker compose run --rm app python scripts/ingest_with_vectors.py --pass all
```

### Si la ingesta se interrumpe a mitad de camino

Cada pase es independiente y utiliza `doc_as_upsert: true`, por lo que se puede reanudar desde donde quedó sin necesidad de empezar de cero:

```bash
# Identifique el último pase completado revisando la salida y comience desde el siguiente.
# Por ejemplo, si terminó metadata + p1_bm25 + p2_bm25 y se cortó en p3_bm25:
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p3_bm25
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p2_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p3_tfidf
docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_splade
```

## Estructura de `vectors/`

La carpeta debe ubicarse en la raíz del proyecto (`2026-1-DS-S1-Grupo10-Backend/vectors/`). Es lo que produce el pipeline de `Vectorizacion/sparse-benchmark/src/pipeline.py`. Los siete archivos esperados son:

| Archivo                        | Preprocesamiento     | Vectorización | Formato                                                               |
|--------------------------------|----------------------|---------------|-----------------------------------------------------------------------|
| `c01_p1_tfidf.json`            | P1 (mínimo)          | TF-IDF        | `[{chunk_id, method, n_nonzero, vector: {token: peso}}, ...]`         |
| `c02_p1_bm25_tokens.json`      | P1 (mínimo)          | BM25          | `{method, ids: [...], tokens: [[...], ...]}`                          |
| `c03_p2_tfidf.json`            | P2 (SpaCy)           | TF-IDF        | idem c01                                                              |
| `c04_p2_bm25_tokens.json`      | P2 (SpaCy)           | BM25          | idem c02                                                              |
| `c05_p3_tfidf.json`            | P3 (Snowball)        | TF-IDF        | idem c01                                                              |
| `c06_p3_bm25_tokens.json`      | P3 (Snowball)        | BM25          | idem c02                                                              |
| `c07_p1_splade.json`           | P1 + WordPiece BERT  | SPLADE        | idem c01, claves son tokens WordPiece (`la`, `##cion`, `##og`, …)     |

`chunk_id` en estos archivos corresponde al UUID del chunk (el mismo `_id` que se utiliza en OpenSearch y Qdrant).

Si el repositorio aún no contiene `vectors/`, se puede generar con el pipeline de la fase de vectorización:

```bash
cd Vectorizacion/sparse-benchmark
pip install -r requirements.txt
python -m spacy download es_core_news_lg
python -m nltk.downloader punkt punkt_tab stopwords
python src/pipeline.py
# Posteriormente, copiar outputs/vectors/* a la carpeta vectors/ del backend.
```

## Cómo funciona la búsqueda

El cliente envía `POST /search` con `{query, method, size, scoring}`. El backend ejecuta los siguientes pasos:

1. Parsea `method` (uno de `p1_bm25`, `p1_tfidf`, `p1_splade`, `p2_bm25`, `p2_tfidf`, `p3_bm25`, `p3_tfidf`).
2. Para BM25 / TF-IDF: aplica el preprocesamiento P1, P2 o P3 a la consulta utilizando la **misma función** del pipeline de vectorización (importada por path desde `src/preprocess_adapter.py`). Para SPLADE: ejecuta el encoder neuronal `naver/splade-cocondenser-ensembledistil` (ver `src/splade_encoder.py`), que produce su propio mapa esparso `{token_wordpiece: peso}` directamente comparable con los vectores indexados.
3. Si la vectorización es BM25: arma una `match` query contra el campo `content_pX[_a|_b|_c]` (texto pre-tokenizado, analyzer `whitespace_lower` que NO modifica los tokens). El BM25 nativo de Lucene asigna el puntaje con los parámetros `k1`/`b` correspondientes a la variante elegida (ver "Tercer eje: función de scoring" más abajo).
4. Si la vectorización es TF-IDF: cuenta `TF(token)` en la consulta y arma una `bool/should` de `rank_feature` queries contra `tfidf_pX.<token>` con `boost = TF`. La función `rank_feature` (linear o saturation con pivot configurable) se selecciona vía `scoring`. **Importante:** la consulta lleva solo TF, no TF·IDF. El IDF queda en el lado del documento (es el patrón "asymmetric TFIDF"). Reproducir TF·IDF en la consulta requeriría serializar el `TfidfVectorizer` ajustado, lo cual no se realiza en esta versión.
5. Si la vectorización es SPLADE: arma una `bool/should` de `rank_feature` queries contra `splade_pX.<token>` con `boost = peso del token en el vector SPLADE de la consulta`. A diferencia de TF-IDF, el encoder ya pondera y expande léxicamente; el boost no es TF crudo sino la activación del modelo. La primera consulta SPLADE de una sesión paga aproximadamente 10 segundos de carga del modelo; las siguientes son de 300-700 ms en CPU.
6. Para cada hit calcula `highlights: {palabra_cruda: score}` mapeando cada palabra del chunk al peso correspondiente del `query_vector` (ejecutando el mismo preprocesador o tokenizador BERT que se usó para la consulta). El frontend lo usa para colorear con un gradiente HSL.
7. Devuelve los top-`k` chunks con su score, metadatos, `content` crudo y `highlights`, además de la **introspección de la query** que el frontend muestra como pipeline de tres etapas:
   - `query`: el texto crudo.
   - `query_input_tokens` (+ `query_input_label`): la etapa 2 del pipeline — cómo la técnica descompone la query. En BM25/TF-IDF es la **salida del preprocesamiento** (P1 regex, P2 lematización SpaCy, P3 stemming Snowball), por eso **difiere entre métodos** y permite compararlos. En SPLADE son los **WordPieces** de la consulta, y en el baseline Qdrant los **stems** Snowball (reconstruidos desde el propio pipeline de fastembed; ya no se muestran los hashes crudos salvo fallback).
   - `query_terms`: el vector esparso listo para mostrar. Cada entrada trae `term` (etiqueta legible), `key` (la clave real usada en el retrieval; el hash MurmurHash3 en el baseline Qdrant), `weight` e `in_query`. **`in_query = false` marca las dimensiones de expansión léxica** que SPLADE agrega y que no están en la consulta original.
   - `query_tokens` (lista de términos/claves que forman el vector) / `query_vector` (`{clave: peso}`): representación histórica, conservada por compatibilidad.

## Tercer eje: función de scoring

El parámetro `scoring` de `/search` permite cambiar la fórmula que el motor aplica al puntuar, sin tocar tokenización ni vectorización. Dos familias según el tipo de campo:

**BM25** (sobre los campos texto `content_pX`): cuatro presets que combinan distintos valores de `k1` (saturación de TF) y `b` (penalización por largo).

| `scoring` | k1 | b | Comportamiento |
|---|---|---|---|
| `default` | 1.2 | 0.75 | Calibración estándar de Lucene |
| `tuned_a` | 1.6 | 0.75 | Saturación más lenta (premia docs que profundizan en un término) |
| `tuned_b` | 2.0 | 0.5 | Saturación muy lenta, menor castigo por largo (favorece docs extensos) |
| `tuned_c` | 0.9 | 1.0 | Saturación rápida, castigo máximo por largo (favorece docs cortos) |

Las cuatro variantes se materializan como **campos hermanos** en el schema: `content_p1`, `content_p1_a`, `content_p1_b`, `content_p1_c` (idem para `p2` y `p3`), todos alimentados desde el campo base vía `copy_to` y cada uno con una similarity distinta declarada en `index.settings.similarity`. Cambiar de variante es query-time, sin reindex.

**Rank-feature** (sobre los campos `tfidf_pX` y `splade_p1`): cinco presets que cambian la función aplicada al peso del documento antes de combinarlo con el boost de la consulta.

| `scoring` | Función | Pivot | Comportamiento |
|---|---|---|---|
| `linear` | linear | — | Sin transformación. Producto punto puro. |
| `saturation_p0_5` | saturation | 0.5 | Aplanamiento fuerte de pesos altos |
| `saturation_p1` | saturation | 1.0 | Aplanamiento moderado |
| `saturation_p5` | saturation | 5.0 | Aplanamiento leve (sweet spot SPLADE) |
| `saturation_p10` | saturation | 10.0 | Casi imperceptible (sanity check ≈ linear) |

Si se omite `scoring`, el backend usa el default por familia (`default` para BM25, `linear` para rank-feature). El catálogo completo lo expone `GET /scoring-variants`, que el frontend consume para poblar el segundo dropdown.

## Endpoints

```
GET  /healthz                  -> {"status": "ok"}
GET  /techniques               -> catálogo de las 7 técnicas (consumido por la UI)
GET  /scoring-variants         -> catálogo de variantes de scoring por familia
POST /search                   -> { query, method, size, scoring? } -> { hits, total, ... }
GET  /                         -> frontend HTML
```

Ejemplo:

```bash
curl -X POST http://localhost:8000/search \
     -H "Content-Type: application/json" \
     -d '{"query":"el arrendatario debe restituir el inmueble","method":"p3_bm25","size":5,"scoring":"tuned_a"}' \
     | python3 -m json.tool
```

## Tests

La suite de tests unitarios fue depurada deliberadamente para concentrarse en los casos con valor real de detección y descartar pruebas tautológicas (que solamente confirman la implementación) o redundantes con la propia validación de Pydantic. La priorización se enfoca en tres clases de fallas con consecuencia silenciosa en producción:

1. **Errores de tipeo en nombres de campo OpenSearch.** Una errata en `tfidf_p1.<token>` produce cero hits sin error visible.
2. **Confusión entre los contratos de TF-IDF (boost por TF) y SPLADE (boost por peso del encoder).** Si se intercambian, el ranking deja de tener sentido pero ningún test estructural lo detecta.
3. **Violaciones de la restricción de `rank_features` que prohíbe valores ≤ 0.** OpenSearch responde 400 en silencio.

Adicionalmente se verifica la consistencia entre el catálogo `config.TECHNIQUES`, los archivos declarados en `VECTOR_FILES` y el `Literal` Pydantic del endpoint `/search`. Si las tres fuentes divergen, el sistema falla de forma sutil al ingestar o atender solicitudes.

No hay tests de integración con OpenSearch ni Qdrant: esa validación se realizará a través de las métricas de retrieval (NDCG@k, MRR, P@k) sobre el conjunto de evaluación, lo cual constituye un criterio más exigente y alineado con los objetivos de la tesis que cualquier suite unitaria.

```bash
# Ejecución local (incluye reporte de cobertura por defecto).
pip install -r requirements-test.txt
pytest

# En CI corre automáticamente en cada push y pull request a main / develop
# (ver .github/workflows/ci.yml).
```

Las dependencias pesadas (spaCy, NLTK, transformers, torch) **no** se instalan en los tests. El módulo `tests/conftest.py` instala stubs ligeros y deterministas con la misma signatura, lo cual mantiene el CI rápido (~30 segundos).

### Cobertura

El reporte de cobertura considera solamente la lógica unit-testeable del backend: `src/config.py`, `src/preprocess_adapter.py`, `src/search.py`, `src/clients.py` y `scripts/api.py`. Quedan deliberadamente excluidos los scripts de integración (`scripts/ingest*.py`, `scripts/create_index.py`) y el encoder SPLADE (`src/splade_encoder.py`), cuya validación natural es la corrida real contra los servicios y, eventualmente, el benchmark con métricas de retrieval. Las exclusiones se declaran en `pyproject.toml` bajo `[tool.coverage.run].omit`.

Cobertura actual: **75.6%** sobre 50 tests cuidadosamente seleccionados (umbral mínimo configurado: 70% — si baja, el CI falla).

| Módulo                       | %     |
|------------------------------|-------|
| `src/config.py`              | 100.0 |
| `src/highlight.py`           |  89.3 |
| `scripts/api.py`             |  84.6 |
| `src/clients.py`             |  71.4 |
| `src/search.py`              |  57.3 |
| `src/preprocess_adapter.py`  |  50.0 |

El número es deliberadamente más bajo que el que produciría una suite inflada con tests triviales. La cobertura no es una meta en sí misma: lo que importa es que cada test conservado documente y enforze un contrato no obvio del sistema. Los puntos del código que aparecen como no cubiertos corresponden a la función `search()` (orquesta la llamada efectiva a OpenSearch) y a las ramas de error y de inicialización del adapter de preprocesamiento, cuya validación se da de forma natural cuando el sistema se ejerce contra los servicios reales. Los scripts del pipeline de benchmarking (`scripts/benchmark/*.py`) están excluidos del cálculo en `[tool.coverage.run].omit` porque su validación natural es la corrida end-to-end contra OpenSearch y Gemini; lo unit-testeable de ellos (parsing del juez, agregación de judgments) se cubre en `tests/test_benchmark_helpers.py`.

## Configuración

Variables de entorno (definidas con valores por defecto razonables en `src/config.py`):

| Variable             | Default                                          | Descripción                                       |
|----------------------|--------------------------------------------------|---------------------------------------------------|
| `OPENSEARCH_HOST`    | `localhost`                                      | host del cluster                                  |
| `OPENSEARCH_PORT`    | `9200`                                           | puerto HTTP                                       |
| `QDRANT_URL`         | `http://localhost:6333`                          | URL del servicio Qdrant                           |
| `QDRANT_COLLECTION`  | `maqui`                                          | nombre de la colección origen                     |
| `BATCH_SIZE`         | `250`                                            | tamaño de batch para scroll + bulk                |
| `VECTORS_DIR`        | `/app/vectors`                                   | carpeta con los archivos precomputados            |
| `VECTORIZACION_PATH` | `/app/sparse_benchmark`                          | path al `src/` de Vectorizacion (para preprocessors) |
| `SPLADE_MODEL`       | `naver/splade-cocondenser-ensembledistil`        | modelo HF para encodear consultas SPLADE          |
| `SPLADE_MAX_LENGTH`  | `256`                                            | máximo de tokens del input SPLADE (truncate)      |

## Estructura del proyecto

```
2026-1-DS-S1-Grupo10-Backend/
├── docker-compose.yml      OpenSearch + Dashboards + Qdrant + servicio app
├── Dockerfile              imagen Python con spaCy es_core_news_lg + NLTK
├── requirements.txt        dependencias del backend (incluye SPLADE)
├── requirements-test.txt   dependencias mínimas para correr pytest
├── pyproject.toml          configuración de ruff, black y pytest
├── README.md
│
├── src/
│   ├── config.py                  constantes, env vars, catálogos de scoring
│   ├── clients.py                 factories de OpenSearch y Qdrant
│   ├── schema.py                  mapping del índice (similarities + campos hermanos)
│   ├── search.py                  lógica de búsqueda parametrizada por scoring
│   ├── highlight.py               highlights ponderados por contribución al score
│   ├── preprocess_adapter.py      importa preprocessors de Vectorizacion/
│   └── splade_encoder.py          encoder SPLADE para query-time
│
├── scripts/
│   ├── create_index.py            crea (o recrea con --force) el índice
│   ├── ingest_with_vectors.py     scroll Qdrant + merge vectors/ → bulk OpenSearch
│   ├── ingest.py                  legacy (solo metadata, sin vectores)
│   └── api.py                     FastAPI + frontend estático
│
├── static/
│   └── index.html          frontend mínimo (vanilla JS)
│
├── tests/
│   ├── conftest.py                 stubs livianos para deps pesadas
│   ├── test_search.py              lógica de construcción de queries
│   ├── test_config.py              consistencia del catálogo de técnicas
│   ├── test_preprocess_adapter.py  (vacío, ver docstring)
│   ├── test_api_models.py          sincronía Pydantic Literal ↔ config.TECHNIQUES
│   └── test_benchmark_helpers.py   parsing del juez LLM y agregación de judgments
│
├── .github/workflows/
│   └── ci.yml              GitHub Actions: lint + format + tests
│
├── vectors/                vectores precomputados (7 archivos, no versionados en git)
│
└── Vectorizacion/
    └── sparse-benchmark/
        └── src/
            ├── preprocessors.py    P1 / P2 / P3 (se importa read-only)
            ├── vectorizers.py
            └── pipeline.py         genera lo que va en vectors/
```

## Notas de diseño

- **OpenSearch agnóstico al preprocesamiento.** El campo `content` original ya no se analiza con `spanish_legal` + hunspell (versiones anteriores). Los campos `content_p1`, `content_p2`, `content_p3` se indexan con el analyzer `whitespace_lower`, que NO modifica los tokens; solo los separa por espacio. Toda la decisión de qué tokenizer/lemmatizer/stemmer utilizar reside en `Vectorizacion/sparse-benchmark/src/preprocessors.py` y se aplica idénticamente al indexar y al consultar.
- **Vectores TF-IDF como `rank_features`.** Cada chunk lleva tres mapas `{token: peso}` precomputados. La consulta utiliza `rank_feature.linear` con boost por TF, lo que produce un scoring asimétrico TF (consulta) × TF·IDF (documento). Cuando se desee reproducir el cálculo offline 1:1, será necesario serializar el `TfidfVectorizer` y deserializarlo al startup de la API.
- **7 técnicas, no 12.** El producto cartesiano completo sería 3 preprocessings × 4 vectorizers = 12, pero por ahora se cuenta con vectores para 7 combinaciones: las 6 de TF-IDF y BM25 sobre P1/P2/P3, más SPLADE en P1 (con tokenización WordPiece propia del modelo, lo cual la vuelve disjunta de las técnicas léxicas; combinarla con P2/P3 no aporta porque el modelo SPLADE re-tokeniza). BGEM3 queda para una etapa siguiente.
- **SPLADE asymmetric vs symmetric.** En la versión actual se utiliza el mismo encoder en lado-doc y lado-query (symmetric SPLADE). Si más adelante se entrena un encoder de consulta distinto del de documento (asymmetric SPLADE, mejor relación calidad-latencia), basta con cambiar `SPLADE_MODEL` por variable de entorno.
- **Reuso del código de Vectorización.** En lugar de duplicar `preprocessors.py`, se monta read-only en el contenedor y se agrega su path a `sys.path`. Cualquier mejora upstream (por ejemplo, cambiar el batch de spaCy) se refleja en el backend con un restart, sin riesgo de drift.
- **`metadata_tipo` y `tribunal` denormalizados.** Conforme al MER v4, los atributos específicos de subtipo (`rol_number`, `bcn_id_norm`, `instance_name`, `court_specific_name`) viven como campos top-level nullable del chunk. La consistencia (qué campos están poblados según `source_type`) se mantiene en la capa de aplicación.
