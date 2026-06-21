"""Genera vectores densos Gemini para las 31 queries del benchmark.

Sigue el patrón exacto que entregó Maqui para embeber el corpus:
modelo `gemini-embedding-001` (3072 dim, verificado contra `out_dense.txt`),
batch via `contents=[...]`, autodetección de credencial por el SDK
(`genai.Client()` sin argumentos lee `GEMINI_API_KEY` del entorno o
cae a ADC si está disponible).

Diferencia con el snippet del corpus: el `task_type`. Maqui embebe los
chunks como `RETRIEVAL_DOCUMENT` (lado-documento de la asimetría); las
queries de búsqueda deben ir como `RETRIEVAL_QUERY` (su comentario
explícito en el snippet original). Si las dos van como
`RETRIEVAL_DOCUMENT` el ranking dense empeora porque el embedding
no aprovecha la asimetría con la que fue entrenado el modelo.

Salidas (en `scripts/benchmark/queries_dense/`):
  - `queries_dense.json`   → `{query_id: [float, ...]}`, fácil de cargar
                              programáticamente.
  - `queries_dense.txt`    → un vector por línea, ordenado por query_id
                              ascendente. Mismo formato que `out_dense.txt`
                              para los chunks del corpus.

Uso (desde la raíz del repo, con `GEMINI_API_KEY` en el `.env`):
    python scripts/benchmark/embed_queries_gemini.py

Si la cuota se agota a mitad, el progreso queda persistido en el JSON
y re-ejecutar continúa desde donde quedó.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
QUERIES_DIR = ROOT / "scripts" / "benchmark" / "queries"
OUT_DIR = ROOT / "scripts" / "benchmark" / "queries_dense"
OUT_JSON = OUT_DIR / "queries_dense.json"
OUT_TXT = OUT_DIR / "queries_dense.txt"

MODEL = "gemini-embedding-001"
# Asimétrico vs RETRIEVAL_DOCUMENT que usa Maqui para los chunks.
TASK_TYPE = "RETRIEVAL_QUERY"
EXPECTED_DIM = 3072

# Tamaño de batch: 31 queries entran en uno, pero dejamos espacio para
# que el código sirva si más adelante el set crece.
BATCH_SIZE = 16

# Pausa entre batches para no chocar contra rate limits del tier libre.
SLEEP_S = 1.0


# -----------------------------------------------------------------------------
# Lógica
# -----------------------------------------------------------------------------


def load_queries() -> list[tuple[str, str]]:
    """Lee los archivos de queries y los devuelve ordenados por query_id."""
    pairs: list[tuple[str, str]] = []
    for path in sorted(QUERIES_DIR.glob("q*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        pairs.append((data["query_id"], data["query_text"]))
    return pairs


def load_existing() -> dict[str, list[float]]:
    """Carga embeddings ya calculados para permitir reanudación."""
    if OUT_JSON.exists():
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    return {}


def embed_batch(client: genai.Client, texts: list[str]) -> list[list[float]]:
    """Embebe un batch siguiendo el patrón exacto que Maqui usó para el corpus."""
    response = client.models.embed_content(
        model=MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=TASK_TYPE),
    )
    vectors: list[list[float]] = []
    for emb in response.embeddings:
        values = list(emb.values)
        if len(values) != EXPECTED_DIM:
            raise RuntimeError(f"dimensión inesperada: {len(values)} (esperado {EXPECTED_DIM})")
        vectors.append(values)
    return vectors


def main() -> int:
    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: ni GEMINI_API_KEY ni GOOGLE_API_KEY en el entorno", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client()  # autodetecta GEMINI_API_KEY como en el snippet de Maqui

    pairs = load_queries()
    print(f"Encontradas {len(pairs)} queries en {QUERIES_DIR.relative_to(ROOT)}")

    existing = load_existing()
    pending = [(qid, text) for qid, text in pairs if qid not in existing]
    if existing:
        print(f"Reanudando: {len(existing)} embeddings ya en {OUT_JSON.name}")
    print(f"Falta embeber: {len(pending)} queries")

    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        qids = [qid for qid, _ in batch]
        texts = [text for _, text in batch]
        print(f"  batch {i // BATCH_SIZE + 1}: {qids[0]}..{qids[-1]} ({len(batch)} items)")
        try:
            vectors = embed_batch(client, texts)
        except Exception as e:
            print(f"FALLO en batch que empieza con {qids[0]}: {e}", file=sys.stderr)
            print("  (guardo lo acumulado y salgo. Re-ejecuta para retomar)", file=sys.stderr)
            break
        for qid, vec in zip(qids, vectors, strict=True):
            existing[qid] = vec
        OUT_JSON.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
        time.sleep(SLEEP_S)

    # Escribir versión .txt sólo si tenemos las 31.
    pairs_ids = [qid for qid, _ in pairs]
    if all(qid in existing for qid in pairs_ids):
        with OUT_TXT.open("w", encoding="utf-8") as f:
            for qid in pairs_ids:
                f.write(str(existing[qid]) + "\n")
        print(f"\nOK: {len(pairs_ids)} embeddings escritos en:")
        print(f"  - {OUT_JSON.relative_to(ROOT)}  (JSON {{query_id: vector}})")
        print(f"  - {OUT_TXT.relative_to(ROOT)}   (una lista por línea, ordenada por qid)")
    else:
        missing = [qid for qid in pairs_ids if qid not in existing]
        print(f"\nFaltan {len(missing)} embeddings: {missing[:5]}...", file=sys.stderr)
        print("  re-ejecuta el script para continuar", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
