# Benchmarking — LLM as a judge

Pipeline para construir ground truth de evaluación usando Gemini como juez,
sobre el pool deduplicado de las 7 técnicas esparsas (y opcionalmente el
baseline denso de Qdrant).

## Escala de relevancia

Se usa la escala TREC estándar de 0 a 3. Es absoluta, no relativa: múltiples
chunks pueden recibir el mismo grado por consulta.

- **0** — Irrelevante: no aborda la consulta.
- **1** — Marginalmente relevante: toca el tema de forma tangencial.
- **2** — Relevante: aporta información útil para responder, no necesariamente exhaustiva.
- **3** — Altamente relevante: responde directa y sustantivamente.

## Estructura de carpetas

```
scripts/benchmark/
├── queries/                  un JSON por query con {query_id, query_text, …}
├── pools/                    salida de retrieve_for_query.py
├── judgments/                salida de judge_pool.py
├── summary.json              salida de ingest_judgments.py (opcional)
├── retrieve_for_query.py
├── judge_pool.py
└── ingest_judgments.py
```

## Setup (una sola vez)

```bash
pip install -r requirements-benchmark.txt
export GEMINI_API_KEY="..."          # obtenida en https://aistudio.google.com/apikey
# Opcional, solo si se va a incluir el baseline denso:
# export OPENAI_API_KEY="..."
```

## Flujo end-to-end para una query

```bash
# 1) Recuperar top-10 por cada técnica esparsa + armar el pool deduplicado.
#    Doble salida: JSON local en pools/ + ingesta al índice retrieval_results
#    en OpenSearch.
python scripts/benchmark/retrieve_for_query.py \
    --query-file scripts/benchmark/queries/q001_prescripcion_cobro.json \
    --output-dir scripts/benchmark/pools \
    --size 10

# 2) Pedir a Gemini que juzgue cada chunk del pool. Toma ~3 min para 50 chunks
#    por el rate limit de la capa gratis (15 req/min).
python scripts/benchmark/judge_pool.py \
    --pool-file scripts/benchmark/pools/q001.json \
    --output-dir scripts/benchmark/judgments

# 3) Ingestar todos los judgments al índice ground_truth + generar resumen.
python scripts/benchmark/ingest_judgments.py \
    --judgments-dir scripts/benchmark/judgments \
    --summary-file scripts/benchmark/summary.json
```

## Índices OpenSearch usados por el benchmark

| Índice                 | Producido por                  | Una fila por                          | Propósito                                                 |
|------------------------|--------------------------------|----------------------------------------|-----------------------------------------------------------|
| `retrieval_results`    | `retrieve_for_query.py`         | (query_id, technique_name)            | Evidencia auditable de qué retornó cada técnica           |
| `ground_truth`         | `ingest_judgments.py`           | (query_id, chunk_uuid)                | Grados de relevancia (0—3) asignados por el LLM           |
| `benchmark_runs` (futuro) | script de métricas a crear   | (query_id, technique_name)            | Recall@k, MRR, NDCG calculados al unir los dos anteriores |

Los IDs determinísticos (`<query_id>::<technique_name>` y `<query_id>::<chunk_uuid>`) garantizan idempotencia: re-correr los scripts sobrescribe en lugar de duplicar.

## Flujo para múltiples queries

Agregue más archivos `*.json` a `queries/` con el mismo formato, y repita los
pasos 1 y 2 para cada uno. El paso 3 procesa toda la carpeta `judgments/` en
una sola corrida.

```bash
for q in scripts/benchmark/queries/*.json; do
    python scripts/benchmark/retrieve_for_query.py \
        --query-file "$q" --output-dir scripts/benchmark/pools --size 10
done

for p in scripts/benchmark/pools/*.json; do
    python scripts/benchmark/judge_pool.py \
        --pool-file "$p" --output-dir scripts/benchmark/judgments
done

python scripts/benchmark/ingest_judgments.py \
    --judgments-dir scripts/benchmark/judgments \
    --summary-file scripts/benchmark/summary.json
```

## Notas operativas

- **Rate limit de Gemini Flash (capa gratis)**: 15 requests/min, 1500/día,
  1M tokens/día. Para un pool típico de 50 chunks × 20 queries = 1000
  requests, alcanza con holgura, pero el tiempo total son ~70 minutos por
  el rate limit.
- **Reproducibilidad**: el pool se aleatoriza con `seed=42` fija. Pasar
  `--no-shuffle` mantiene el orden de aparición original (útil para debug,
  pero introduce sesgo de posición en el juez).
- **Idempotencia**: cada judgment se indexa con id `<query_id>::<chunk_uuid>`,
  por lo que re-correr `ingest_judgments.py` sobreescribe en lugar de duplicar.
- **Judgments fallidos**: si Gemini devuelve algo no parseable, el judgment se
  marca con `relevance_grade=-1` y `justification="PARSE_ERROR: ..."`. El
  resumen los cuenta aparte y no contaminan la distribución de grados.
- **Baseline denso**: agregue `--with-qdrant` al paso 1 si tiene
  `OPENAI_API_KEY` y la librería `openai` instalada. Sin esto, el baseline se
  omite y el pool incluye únicamente las técnicas esparsas.
