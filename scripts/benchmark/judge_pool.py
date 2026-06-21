"""LLM-as-a-judge: pide a Gemini que evalúe la relevancia de cada chunk del pool.

Usa la capa gratis de Gemini API (`gemini-2.0-flash` por defecto), que tiene
15 RPM y 200 RPD — el mejor compromiso entre rate limit y volumen diario en
capa gratis al momento de escribir esto. Para un pool típico de 50 chunks
únicos, el tiempo total es ~3.5 minutos por query.

Modelos alternativos y sus límites en capa gratis:
  - gemini-2.0-flash      : 15 RPM, 200 RPD ← default
  - gemini-2.5-flash      :  5 RPM,  20 RPD  (más nuevo, pero severamente limitado)
  - gemini-1.5-flash      : DEPRECADO en 2025
  - gemini-2.0-flash-lite : 30 RPM, 200 RPD (alternativa más rápida)

Manejo de rate limit:
  - Sleep fijo de RATE_LIMIT_SLEEP segundos entre requests para respetar RPM.
  - Si igual aparece `ResourceExhausted`, el script parsea el `retry_delay`
    del error de Google y duerme exactamente esa cantidad antes de reintentar
    el MISMO chunk (no lo marca como fallido).
  - Hasta MAX_RETRIES_ON_RATE_LIMIT intentos por chunk. Pasado eso, el chunk
    queda con grade=-1 y el script sigue (no aborta).

Salida (JSON en judgments/):
{
  "query_id": "...",
  "query_text": "...",
  "model": "gemini-1.5-flash",
  "judgments": [
    {
      "chunk_uuid": "...",
      "relevance_grade": <0|1|2|3>,
      "justification": "..."
    },
    ...
  ]
}

**Modo incremental por default**: si ya existe el archivo de judgments
para esta query, se preservan los grados válidos (0-3) y solo se juzgan
los chunks nuevos del pool o los que tenían grade=-1 en la corrida
anterior. Esto ahorra cuota de Gemini cuando el pool creció tras
re-ejecutar retrieve. Pase `--no-merge` para forzar re-juzgar todo.

Uso:
    export GEMINI_API_KEY=...
    python scripts/benchmark/judge_pool.py \\
        --pool-file scripts/benchmark/pools/q001.json \\
        --output-dir scripts/benchmark/judgments
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Logger con timestamp para que se distingan los mensajes del progreso
# chunk-por-chunk de los errores reales.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("judge_pool")


# Códigos / nombres de excepciones que indican un problema sistémico:
# fallan en TODO el pool y no tiene sentido seguir intentando. Cuando se
# acumulan varios de estos seguidos, el script aborta con un mensaje
# accionable en lugar de generar 36 judgments con relevance_grade=-1.
_SYSTEMIC_ERROR_MARKERS = (
    "NotFound",  # 404: modelo inexistente o deprecado
    "PermissionDenied",  # 403: cuenta sin acceso al modelo
    "Unauthenticated",  # 401: API key inválida o expirada
    "InvalidArgument",  # 400: prompt mal formado, prohibido por safety, etc.
    "FailedPrecondition",  # configuración del proyecto
)

# Si se observan N fallos consecutivos con un mismo error sistémico, abortar.
_ABORT_AFTER_CONSECUTIVE_SYSTEMIC = 3


# Se omite el ejemplo de grado 1 para disminuir sesgo
PROMPT_TEMPLATE = """Eres un experto en derecho chileno especializado en materia \
inmobiliaria (arrendamientos, compraventa, copropiedad, propiedad horizontal, \
tributación de inmuebles, recursos sobre bienes raíces).

Las consultas que vas a evaluar provienen del sector inmobiliario y pueden \
tocarse con cualquier fuente del corpus: oficios y circulares del SII, leyes de \
la BCN, resoluciones administrativas o jurisprudencia de tribunales chilenos. \
Todas las fuentes pueden ser relevantes si abordan la materia consultada.

Tu tarea: dado un fragmento de documento legal, decidir qué tan relevante es \
para responder la consulta del usuario.

ESCALA (criterio absoluto; múltiples fragmentos pueden recibir el mismo grado, \
no fuerces distinciones artificiales):

  0 — Irrelevante. No aborda la consulta ni una materia adyacente.
  1 — Marginalmente relevante. Toca tangencialmente el tema pero no responde la consulta.
  2 — Relevante. Aporta información útil para responder, aunque no sea exhaustiva. \
Cita el tema, lo define, o lo discute parcialmente. Es el grado por defecto para \
fragmentos que TRATAN sobre la consulta.
  3 — **Altamente relevante (uso reservado)**. El fragmento CONTIENE la respuesta \
principal de la consulta. Un usuario que lee este fragmento aprende la respuesta sin \
necesidad de leer nada más. NO basta con citar el artículo o el concepto: el fragmento \
debe explicarlo o aplicarlo sustantivamente. **Si dudas entre 2 y 3, elige 2.**

CRITERIOS ADICIONALES:
  - Importa la pertinencia, no el largo.
  - Para jurisprudencia, evalúa si la doctrina del fallo aborda la consulta.
  - Para oficios o circulares, evalúa si la interpretación administrativa responde.
  - Para leyes, evalúa si el articulado citado es el aplicable a la consulta.
  - Un fragmento que define un concepto central de la consulta pero no detalla su \
aplicación suele ser grado 2, no 3.

<ejemplos>
<ejemplo grado="3" comentario="altamente relevante, criterio estricto">
<consulta>Obligaciones del arrendatario al término del contrato</consulta>
<fragmento>Al término del contrato de arrendamiento, el arrendatario deberá: \
(i) restituir el inmueble en el mismo estado en que lo recibió, salvo el deterioro \
por uso legítimo; (ii) pagar las rentas adeudadas hasta la fecha de restitución; \
(iii) cubrir los daños no atribuibles al uso normal de la cosa...</fragmento>
<respuesta>{{"justification": "Enumera las tres obligaciones específicas del \
arrendatario al término del contrato, respondiendo la consulta exhaustivamente.", \
"relevance_grade": 3}}</respuesta>
</ejemplo>
<ejemplo grado="2" comentario="relevante; NO grado 3 a pesar de citar el tema">
<consulta>Obligaciones del arrendatario al término del contrato</consulta>
<fragmento>El arrendatario está obligado a restituir el inmueble al término del \
contrato, conforme al artículo 1947 del Código Civil...</fragmento>
<respuesta>{{"justification": "Cita la obligación de restitución pero no la \
desarrolla; menciona el tema sin explicarlo sustantivamente.", "relevance_grade": 2}}</respuesta>
</ejemplo>
<ejemplo grado="0" comentario="irrelevante">
<consulta>Obligaciones del arrendatario al término del contrato</consulta>
<fragmento>Las sociedades anónimas deberán constituirse por escritura pública \
otorgada ante notario...</fragmento>
<respuesta>{{"justification": "Materia societaria, sin relación con \
arrendamientos.", "relevance_grade": 0}}</respuesta>
</ejemplo>
</ejemplos>

AHORA EVALÚA:

<consulta>
{query}
</consulta>

<fragmento documento="{name}" tipo="{source_type}">
{content}
</fragmento>

Responde estrictamente en JSON con la forma exacta (justification primero, grade después):
{{"justification": "<frase de 10-25 palabras en español>", "relevance_grade": <0|1|2|3>}}
"""


# Límite por chunk antes de enviar al juez. Se eligió 5000 caracteres porque
# el chunker upstream ya capa los chunks alrededor de 4000 chars (máximo
# observado en pools reales: 3,961). Con el valor previo de 3000 quedaba
# truncado el 83% de los chunks, perdiendo ~700-900 caracteres del final
# antes de que el juez los viera y sesgando la decisión a la primera parte
# del fragmento. 5000 captura el 100% de los chunks típicos y deja margen
# de ~25% para outliers, sin acercarse al límite de contexto del modelo
# (gemini-2.5-flash-lite tiene 1M tokens).
CONTENT_MAX_CHARS = 5000
RATE_LIMIT_SLEEP = 4.1  # 15 req/min ≈ 1 req cada 4s; 4.1 para tener margen.

# Cantidad de chunks a juzgar en una sola llamada al LLM. Default 5 reduce
# las llamadas al API en 5x respecto del modo per-chunk. Con la cuota
# diaria de 200 requests (gemini-2.0-flash free tier), 8 calls por query
# de ~36 chunks permite ~25 queries/día vs ~5 sin batching.
BATCH_SIZE = 5

# Si Gemini devuelve 429 ResourceExhausted, reintentamos hasta esta cantidad de
# veces el mismo chunk/batch (durmiendo el `retry_delay` que el error informe,
# o `RATE_LIMIT_FALLBACK_SLEEP` si no se puede parsear).
MAX_RETRIES_ON_RATE_LIMIT = 2
RATE_LIMIT_FALLBACK_SLEEP = 60  # segundos


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _truncate_content(content: str, chunk_uuid: str) -> str:
    """Recorta el contenido a CONTENT_MAX_CHARS dejando un WARNING auditable.

    Antes el recorte era silencioso (`content[:CONTENT_MAX_CHARS]`): un chunk
    de 8000 caracteres llegaba al juez como 3000 sin que nadie se enterara, y
    el grado se emitia sobre un fragmento incompleto. Ahora se registra un
    warning con el uuid y los caracteres perdidos para que el recorte sea
    visible en el log y se pueda decidir si subir el limite o partir el chunk.
    """
    if len(content) <= CONTENT_MAX_CHARS:
        return content
    logger.warning(
        "Chunk %s recortado de %d a %d caracteres (%d perdidos) para no inflar "
        "el prompt; el juez evaluara solo el fragmento truncado.",
        chunk_uuid[:8],
        len(content),
        CONTENT_MAX_CHARS,
        len(content) - CONTENT_MAX_CHARS,
    )
    return content[:CONTENT_MAX_CHARS]


def _parse_retry_delay(error_message: str) -> int | None:
    """Extrae los segundos de espera de un error 429 de Gemini.

    El mensaje de Google viene con un campo `retry_delay { seconds: N }`
    en la representación protobuf. Lo parseamos con regex (más simple que
    importar las clases protobuf solo para esto). Devuelve None si no se
    encuentra; el caller usa RATE_LIMIT_FALLBACK_SLEEP como respaldo.
    """
    import re

    m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", error_message)
    if m:
        return int(m.group(1))
    # Variante "Please retry in 35.965s" que aparece en la cabecera.
    m = re.search(r"retry in (\d+)", error_message)
    if m:
        return int(m.group(1))
    return None


def _is_rate_limit_error(exception: BaseException) -> bool:
    """Detecta 429 / ResourceExhausted en distintas formas en que Gemini lo expone."""
    name = type(exception).__name__
    msg = str(exception)
    return "ResourceExhausted" in name or "429" in msg or "ResourceExhausted" in msg


def _is_daily_quota_exhausted(exception: BaseException) -> bool:
    """Distingue cuota diaria (no se recupera durmiendo) de rate limit por minuto."""
    msg = str(exception)
    return (
        "PerDay" in msg
        or "GenerateRequestsPerDayPerProjectPerModel" in msg
        or "RequestsPerDay" in msg
    )


def _is_free_tier_disabled(exception: BaseException) -> bool:
    """Detecta el caso `limit: 0` que indica que Google deshabilitó el free
    tier para este modelo (no que el usuario gastó su cuota).

    Cuando Google retira el free tier de un modelo, devuelve el mismo 429
    pero con `limit: 0` en la métrica. El usuario no consumió nada — la
    cuota es 0 desde el inicio. Esperar al reset no ayuda; hay que cambiar
    de modelo o habilitar billing.
    """
    msg = str(exception)
    return "limit: 0" in msg and "free_tier" in msg


def _build_batch_prompt(query: str, chunks: list[dict]) -> str:
    """Arma el prompt para juzgar N chunks en una sola llamada.

    Reusa la escala y los criterios del prompt single-chunk pero
    pidiendo un JSON ARRAY de N objetos en lugar de uno solo.
    Mantiene la regla "si dudas entre 2 y 3, elige 2" para que el LLM
    siga siendo conservador con el grado 3.
    """
    fragments_block = ""
    for idx, chunk in enumerate(chunks, 1):
        name = chunk.get("name") or "(sin nombre)"
        source_type = chunk.get("source_type") or "(desconocido)"
        content = _truncate_content(chunk.get("content") or "", chunk["chunk_uuid"])
        fragments_block += (
            f'\n<fragmento n="{idx}" chunk_uuid="{chunk["chunk_uuid"]}" '
            f'documento="{name}" tipo="{source_type}">\n'
            f"{content}\n"
            f"</fragmento>\n"
        )

    return f"""Eres un experto en derecho chileno especializado en materia inmobiliaria \
(arrendamientos, compraventa, copropiedad, propiedad horizontal, tributación de \
inmuebles, recursos sobre bienes raíces).

Las consultas que vas a evaluar provienen del sector inmobiliario y pueden tocarse \
con cualquier fuente del corpus: oficios y circulares del SII, leyes de la BCN, \
resoluciones administrativas o jurisprudencia de tribunales chilenos.

<consulta>
{query}
</consulta>

A continuación hay {len(chunks)} fragmentos numerados. Evalúa cada uno con la \
siguiente escala absoluta:

  0 — Irrelevante. No aborda la consulta ni una materia adyacente.
  1 — Marginalmente relevante. Toca tangencialmente el tema pero no responde.
  2 — Relevante. Trata sobre el tema, lo define o lo discute parcialmente. \
**Es el grado por defecto para fragmentos que tratan sobre la consulta.**
  3 — Altamente relevante (USO RESERVADO). El fragmento CONTIENE la respuesta \
principal; un usuario aprende la respuesta sin leer nada más. NO basta con citar \
el artículo. **Si dudas entre 2 y 3, elige 2.**

No penalices ni premies por extensión. Múltiples fragmentos pueden recibir el \
mismo grado.

<fragmentos>
{fragments_block}
</fragmentos>

Responde estrictamente con un JSON ARRAY de exactamente {len(chunks)} objetos, \
EN EL MISMO ORDEN que los fragmentos arriba. Cada objeto tiene la forma exacta:

[
  {{"chunk_uuid": "<el chunk_uuid del fragmento 1>", "justification": "<frase de 10-25 palabras>", "relevance_grade": <0|1|2|3>}},
  {{"chunk_uuid": "<el chunk_uuid del fragmento 2>", "justification": "<frase de 10-25 palabras>", "relevance_grade": <0|1|2|3>}},
  ...
]
"""


def _chunked(items: list, n: int) -> list[list]:
    """Divide `items` en sublistas de a lo más `n` elementos."""
    return [items[i : i + n] for i in range(0, len(items), n)]


class DailyQuotaExhausted(Exception):
    """Se levanta cuando Gemini reporta que la cuota DIARIA está agotada.
    A diferencia del rate limit por minuto, esperar no ayuda: la cuota se
    resetea a medianoche UTC. El caller debe abortar y avisar al usuario.
    """


class FreeTierDisabled(Exception):
    """Se levanta cuando Google retiró el free tier para el modelo solicitado
    (la cuota es `limit: 0`). Cambiar de key no ayuda — hay que cambiar de
    modelo (a uno con free tier vigente, p.ej. los `-lite`) o habilitar
    billing en el proyecto.
    """


def _parse_batch_response(raw: str, batch: list[dict]) -> list[dict]:
    """Parsea la respuesta del LLM (array de N judgments) y la asocia con
    los chunks originales. Si el LLM devolvió menos items o uuids que no
    están en el batch, los chunks faltantes quedan con grade=-1.
    """
    arr = json.loads(raw)
    if not isinstance(arr, list):
        raise ValueError(f"esperado array, recibido {type(arr).__name__}")

    # Indexamos por uuid para tolerar respuestas fuera de orden o incompletas.
    by_uuid: dict[str, dict] = {}
    for item in arr:
        uuid = item.get("chunk_uuid")
        if not uuid:
            continue
        grade = int(item["relevance_grade"])
        if grade not in (0, 1, 2, 3):
            continue
        by_uuid[uuid] = {
            "chunk_uuid": uuid,
            "relevance_grade": grade,
            "justification": str(item.get("justification", "")).strip(),
        }

    out = []
    for chunk in batch:
        uuid = chunk["chunk_uuid"]
        if uuid in by_uuid:
            out.append(by_uuid[uuid])
        else:
            out.append(
                {
                    "chunk_uuid": uuid,
                    "relevance_grade": -1,
                    "justification": "PARSE_ERROR: chunk omitido o malformado en la respuesta batch",
                }
            )
    return out


def judge_batch(model, query: str, batch: list[dict]) -> list[dict]:
    """Juzga N chunks en una sola llamada al LLM, con retry sobre rate limit.

    Estrategia:
      - Una sola llamada por batch.
      - Si la cuota DIARIA está agotada, levanta DailyQuotaExhausted (el
        caller aborta limpio).
      - Si es rate limit por minuto, duerme el retry_delay reportado y
        reintenta hasta MAX_RETRIES_ON_RATE_LIMIT veces.
      - Si todo falla, marca el batch entero con grade=-1.
    """
    prompt = _build_batch_prompt(query, batch)
    last_exception: BaseException | None = None

    for attempt in range(MAX_RETRIES_ON_RATE_LIMIT + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
            raw = _strip_markdown_fences(response.text)
            return _parse_batch_response(raw, batch)
        except Exception as e:  # noqa: BLE001
            last_exception = e
            if _is_free_tier_disabled(e):
                # `limit: 0` — Google deshabilitó el free tier para este
                # modelo. Cambiar de key no ayuda. Abortamos limpio.
                raise FreeTierDisabled(str(e)) from e
            if _is_daily_quota_exhausted(e):
                # Cuota diaria — esperar no ayuda. Propagamos para abort.
                raise DailyQuotaExhausted(str(e)) from e
            if _is_rate_limit_error(e) and attempt < MAX_RETRIES_ON_RATE_LIMIT:
                delay = _parse_retry_delay(str(e)) or RATE_LIMIT_FALLBACK_SLEEP
                delay += 2  # margen
                logger.warning(
                    "Rate limit en batch (intento %d/%d). Durmiendo %ds antes de reintentar...",
                    attempt + 1,
                    MAX_RETRIES_ON_RATE_LIMIT,
                    delay,
                )
                time.sleep(delay)
                continue
            break

    # Si llegamos acá, agotamos retries o fue un parse error.
    err_str = f"{type(last_exception).__name__}: {last_exception}"
    return [
        {
            "chunk_uuid": chunk["chunk_uuid"],
            "relevance_grade": -1,
            "justification": f"PARSE_ERROR (batch): {err_str}",
        }
        for chunk in batch
    ]


def judge_chunk(model, query: str, chunk: dict) -> dict:
    """Llama al juez con reintentos sobre rate limit.

    Si Gemini devuelve `ResourceExhausted` (429), parsea el `retry_delay`
    del propio error y duerme esa cantidad antes de reintentar el mismo
    chunk. Se reintenta hasta MAX_RETRIES_ON_RATE_LIMIT veces. Otros
    errores (parse, ValueError) NO se reintentan — se marcan con grade=-1.
    """
    prompt = PROMPT_TEMPLATE.format(
        query=query,
        name=chunk.get("name") or "(sin nombre)",
        source_type=chunk.get("source_type") or "(desconocido)",
        content=_truncate_content(chunk.get("content") or "", chunk["chunk_uuid"]),
    )

    last_exception: BaseException | None = None
    for attempt in range(MAX_RETRIES_ON_RATE_LIMIT + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
            raw = _strip_markdown_fences(response.text)
            data = json.loads(raw)
            grade = int(data["relevance_grade"])
            if grade not in (0, 1, 2, 3):
                raise ValueError(f"grado fuera de rango: {grade}")
            return {
                "chunk_uuid": chunk["chunk_uuid"],
                "relevance_grade": grade,
                "justification": str(data.get("justification", "")).strip(),
            }
        except Exception as e:  # noqa: BLE001
            last_exception = e
            if _is_rate_limit_error(e) and attempt < MAX_RETRIES_ON_RATE_LIMIT:
                delay = _parse_retry_delay(str(e)) or RATE_LIMIT_FALLBACK_SLEEP
                # Sumamos 2s de margen al delay que reportó Google para evitar
                # caer justo en el borde del cuota y rebotar otra vez.
                delay += 2
                logger.warning(
                    "Rate limit alcanzado en chunk %s (intento %d/%d). "
                    "Durmiendo %ds antes de reintentar...",
                    chunk["chunk_uuid"][:8],
                    attempt + 1,
                    MAX_RETRIES_ON_RATE_LIMIT,
                    delay,
                )
                time.sleep(delay)
                continue
            break

    # Si llegamos acá, agotamos los reintentos o el error no es de rate limit.
    return {
        "chunk_uuid": chunk["chunk_uuid"],
        "relevance_grade": -1,
        "justification": f"PARSE_ERROR: {type(last_exception).__name__}: {last_exception}",
    }


def _load_existing_judgments(output_dir: Path, query_id: str) -> dict[str, dict]:
    """Lee judgments preexistentes y los devuelve indexados por chunk_uuid.

    Devuelve {} si el archivo no existe. Solo retiene judgments con
    `relevance_grade != -1` (los grados válidos): los PARSE_ERROR se
    re-intentan en la corrida nueva porque no aportaron información
    relevante la primera vez.
    """
    path = output_dir / f"{query_id}_judgments.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return {
        j["chunk_uuid"]: j for j in data.get("judgments", []) if j.get("relevance_grade", -1) != -1
    }


def main(
    pool_file: Path,
    output_dir: Path,
    model_name: str,
    batch_size: int,
    merge_existing: bool = True,
) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("[x] falta GEMINI_API_KEY en el entorno.")

    try:
        import google.generativeai as genai
    except ImportError:
        sys.exit(
            "[x] falta la librería google-generativeai. Instale con "
            "`pip install -r requirements-benchmark.txt`."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    pool_data = json.loads(pool_file.read_text())
    query_id = pool_data["query_id"]
    query_text = pool_data["query_text"]
    pool = pool_data["pool"]

    # Modo incremental: separa chunks ya juzgados con grado válido del resto.
    # Los chunks con grade=-1 (PARSE_ERROR) sí se re-juzgan porque no aportaron
    # información en la corrida previa.
    existing: dict[str, dict] = {}
    if merge_existing:
        existing = _load_existing_judgments(output_dir, query_id)
        if existing:
            already_judged = sum(1 for c in pool if c["chunk_uuid"] in existing)
            print(
                f"[{query_id}] modo incremental: {already_judged} de {len(pool)} "
                f"chunks ya tienen judgment válido, se saltean."
            )
            pool = [c for c in pool if c["chunk_uuid"] not in existing]
        else:
            print(
                f"[{query_id}] modo incremental: no hay judgments previos válidos, "
                "juzgo todo el pool."
            )

    if not pool:
        print(f"[{query_id}] nada que juzgar — todos los chunks ya tienen grado.")
        # Sigo escribiendo el archivo para que sea idempotente:
        # los existing se preservan tal cual.
        judgments = list(existing.values())
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{query_id}_judgments.json"
        out_path.write_text(
            json.dumps(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "model": model_name,
                    "judged_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "judgments": judgments,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"OK -> {out_path}  (sin llamadas al LLM)")
        return

    batches = _chunked(pool, batch_size)
    print(
        f"[{query_id}] juzgando {len(pool)} chunks en {len(batches)} batches "
        f"de hasta {batch_size} con {model_name}"
    )
    print(
        f"  rate limit aprox: 15 req/min → "
        f"~{len(batches) * RATE_LIMIT_SLEEP / 60:.1f} min total"
    )

    judgments: list[dict] = []
    consecutive_systemic = 0
    last_systemic_error = ""

    for i, batch in enumerate(batches, 1):
        print(
            f"  [batch {i:>3}/{len(batches)}] {len(batch)} chunks...",
            end=" ",
            flush=True,
        )
        t0 = time.time()
        try:
            batch_judgments = judge_batch(model, query_text, batch)
        except FreeTierDisabled as e:
            print()
            logger.error("")
            logger.error("=" * 70)
            logger.error(
                "ABORTANDO: Google deshabilitó el FREE TIER para %s.",
                model_name,
            )
            logger.error("")
            logger.error("Detalle COMPLETO del error de Google:")
            logger.error("-" * 70)
            logger.error("%s", str(e))
            logger.error("-" * 70)
            logger.error("")
            logger.error("Diagnóstico:")
            logger.error("  El error dice `limit: 0` — la cuota gratis de este modelo es CERO.")
            logger.error("  No es que se agotó: nunca hubo. Crear más keys no ayuda.")
            logger.error("")
            logger.error("Salidas:")
            logger.error("  1) Cambie a un modelo con free tier vigente. Sugerencias:")
            logger.error("       --model gemini-2.5-flash-lite   (15 RPM, 1000 RPD)")
            logger.error("       --model gemini-2.0-flash-lite   (30 RPM, 200 RPD)")
            logger.error("       --model gemini-2.5-flash        ( 5 RPM,  25 RPD)")
            logger.error("  2) Active Tier 1 (billing, ~US$5 de crédito) en")
            logger.error("       https://aistudio.google.com/app/apikey")
            sys.exit(1)
        except DailyQuotaExhausted as e:
            print()
            logger.error("")
            logger.error("=" * 70)
            logger.error("ABORTANDO: cuota DIARIA de Gemini agotada.")
            logger.error("")
            logger.error("Detalle COMPLETO del error de Google:")
            logger.error("-" * 70)
            logger.error("%s", str(e))
            logger.error("-" * 70)
            logger.error("")
            logger.error("Diagnóstico:")
            logger.error("  La cuota diaria solo se resetea a medianoche UTC.")
            logger.error("  Esperar no tiene sentido — vuelva mañana o use otra API key.")
            logger.error("  Capa gratis de %s: ~200 RPD.", model_name)
            logger.error(
                "  Tip: con batch_size=%d ya se reducen las llamadas en %dx; "
                "este día la cuenta ya las consumió.",
                batch_size,
                batch_size,
            )
            sys.exit(1)

        judgments.extend(batch_judgments)
        elapsed = time.time() - t0
        grade_counts = {
            g: sum(1 for j in batch_judgments if j["relevance_grade"] == g)
            for g in (3, 2, 1, 0, -1)
        }
        summary = ", ".join(f"{g}:{c}" for g, c in grade_counts.items() if c > 0)
        print(f"grades {{{summary}}}  ({elapsed:.1f}s)")

        # Detección de errores sistémicos: si TODO el batch falló con un
        # marcador sistémico, acumulamos consecutivos para abortar temprano.
        if all(j["relevance_grade"] == -1 for j in batch_judgments):
            justification = batch_judgments[0].get("justification", "")
            if any(marker in justification for marker in _SYSTEMIC_ERROR_MARKERS):
                consecutive_systemic += 1
                last_systemic_error = justification
                logger.error(
                    "Batch entero con error sistémico (batch %d/%d): %s",
                    i,
                    len(batches),
                    justification[:200],
                )
                if consecutive_systemic >= _ABORT_AFTER_CONSECUTIVE_SYSTEMIC:
                    logger.error("")
                    logger.error("=" * 70)
                    logger.error(
                        "ABORTANDO: %d batches consecutivos con el mismo error.",
                        consecutive_systemic,
                    )
                    logger.error("Último error: %s", last_systemic_error[:300])
                    logger.error("")
                    if "NotFound" in last_systemic_error:
                        logger.error(
                            "  Modelo '%s' no existe. Pruebe --model gemini-2.0-flash",
                            model_name,
                        )
                    elif "PermissionDenied" in last_systemic_error:
                        logger.error("  API key sin acceso. Revise AI Studio.")
                    elif "Unauthenticated" in last_systemic_error:
                        logger.error("  API key inválida. Regenere y re-exporte.")
                    elif "InvalidArgument" in last_systemic_error:
                        logger.error(
                            "  Prompt rechazado (probablemente safety). "
                            "Revise el contenido de los chunks."
                        )
                    sys.exit(1)
        else:
            consecutive_systemic = 0

        if i < len(batches):
            time.sleep(RATE_LIMIT_SLEEP)

    # Si veníamos en modo incremental, antepone los judgments preexistentes
    # válidos a los nuevos. Así el archivo de salida queda con TODOS los
    # chunks del pool original, no solo los recién juzgados.
    if existing:
        judgments = list(existing.values()) + judgments
        print(
            f"  merged: {len(existing)} preservados + {len(judgments) - len(existing)} nuevos "
            f"= {len(judgments)} judgments totales"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{query_id}_judgments.json"
    out_path.write_text(
        json.dumps(
            {
                "query_id": query_id,
                "query_text": query_text,
                "model": model_name,
                "judged_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "judgments": judgments,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash",
        help="Modelo Gemini a usar. Default: gemini-2.0-flash (15 RPM, 200 RPD en capa gratis)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=(
            f"Chunks por llamada al LLM. Default {BATCH_SIZE} (reduce 5x las "
            "llamadas vs uno por uno). Pase 1 para volver al modo per-chunk."
        ),
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help=(
            "Desactiva el modo incremental (que es el default). Por default, "
            "si ya existe `<output-dir>/<query_id>_judgments.json`, se "
            "preservan los judgments válidos (grado 0-3) y solo se juzgan "
            "los chunks nuevos o los que tenían grade=-1 (PARSE_ERROR) en "
            "la corrida anterior. Pase --no-merge para forzar re-juzgar "
            "TODO el pool desde cero (raramente necesario; útil si quiere "
            "regenerar judgments con un prompt nuevo o un modelo distinto)."
        ),
    )
    args = parser.parse_args()

    main(
        pool_file=args.pool_file,
        output_dir=args.output_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        merge_existing=not args.no_merge,
    )
