"""Ingesta los chunks_maqui mergeando metadata de Qdrant + vectores en `vectors/`.

Ingesta por pases (uno por archivo) para evitar tener los archivos cargados en
memoria a la vez. Cada pase carga UN archivo, hace bulk-update parcial sobre
OpenSearch y libera la memoria.

Pases disponibles:
    metadata       scroll Qdrant -> bulk INDEX (crea los docs con metadata + content)
    p1_bm25        carga c02_p1_bm25_tokens.json -> UPDATE content_p1
    p2_bm25        carga c04_p2_bm25_tokens.json -> UPDATE content_p2
    p3_bm25        carga c06_p3_bm25_tokens.json -> UPDATE content_p3
    p1_tfidf       carga c01_p1_tfidf.json       -> UPDATE tfidf_p1
    p2_tfidf       carga c03_p2_tfidf.json       -> UPDATE tfidf_p2
    p3_tfidf       carga c05_p3_tfidf.json       -> UPDATE tfidf_p3
    p1_splade      carga c07_p1_splade.json      -> UPDATE splade_p1
    all            corre todos los pases anteriores en orden

Los UPDATE usan `doc_as_upsert: true`, así que el orden no importa estrictamente
(es posible ejecutar p1_tfidf antes que metadata y se crea el doc con solo ese
campo; luego metadata lo completa). Sin embargo, se recomienda partir por
metadata.

Uso:
    docker compose run --rm app python scripts/ingest_with_vectors.py
    docker compose run --rm app python scripts/ingest_with_vectors.py --pass all
    docker compose run --rm app python scripts/ingest_with_vectors.py --pass metadata
    docker compose run --rm app python scripts/ingest_with_vectors.py --pass p3_bm25
    docker compose run --rm app python scripts/ingest_with_vectors.py --pass p1_tfidf --limit 1000
"""

import argparse
import gc
import re
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opensearchpy.helpers import streaming_bulk
from src import clients, config
from tqdm import tqdm

# --- JSON loader: orjson si está disponible (3-5x más rápido), si no stdlib --
try:
    import orjson as _orjson  # type: ignore

    def _load_json_file(path: Path) -> Any:
        with open(path, "rb") as f:
            return _orjson.loads(f.read())

    _JSON_BACKEND = "orjson"
except ImportError:
    import json as _stdjson

    def _load_json_file(path: Path) -> Any:
        with open(path, encoding="utf-8") as f:
            return _stdjson.load(f)

    _JSON_BACKEND = "stdlib json"


# --- Helpers metadata --------------------------------------------------------

_EXTERNAL_ID_RE = re.compile(r"_(\d+)_")


def parse_external_id(filename: str | None) -> int | None:
    if not filename:
        return None
    m = _EXTERNAL_ID_RE.search(filename)
    return int(m.group(1)) if m else None


def _nullify(value: Any) -> Any:
    if value == "" or value == 0:
        return None
    return value


def _bulk(client, actions: Iterable[dict], desc: str, total: int | None) -> None:
    """Wrapper común para streaming_bulk con tqdm y conteo de fallos."""
    pbar = tqdm(total=total, desc=desc, unit="op")
    ok = 0
    fail = 0
    for success, info in streaming_bulk(
        client,
        actions,
        chunk_size=config.BATCH_SIZE,
        raise_on_error=False,
        raise_on_exception=False,
        yield_ok=True,
    ):
        pbar.update(1)
        if success:
            ok += 1
        else:
            fail += 1
            if fail <= 3:
                pbar.write(f"[fail] {info}")
    pbar.close()
    print(f"  ok: {ok:,}   fail: {fail:,}")


def _iter_bm25_updates(
    chunk_ids: list[Any],
    chunk_tokens: list[Any],
    field: str,
) -> Iterable[dict]:
    """Acciones bulk para BM25."""
    for uuid, toks in zip(chunk_ids, chunk_tokens, strict=False):
        if not uuid:
            continue
        joined = " ".join(toks) if toks else ""
        yield {
            "_op_type": "update",
            "_index": config.INDEX_CHUNKS,
            "_id": uuid,
            "doc": {field: joined},
            "doc_as_upsert": True,
        }


def _iter_rank_feature_updates(entries: list[Any], field: str) -> Iterable[dict]:
    """Acciones bulk para TF-IDF / SPLADE."""
    for entry in entries:
        uuid = entry.get("chunk_id")
        if not uuid:
            continue
        vec = entry.get("vector") or {}
        clean = {tok: float(w) for tok, w in vec.items() if w > 0}
        yield {
            "_op_type": "update",
            "_index": config.INDEX_CHUNKS,
            "_id": uuid,
            "doc": {field: clean},
            "doc_as_upsert": True,
        }


# --- Pase: metadata ----------------------------------------------------------


def _metadata_doc_from_point(point: Any) -> dict:
    pl = point.payload or {}
    content = pl.get("content") or ""
    return {
        "chunk_uuid": str(point.id),
        "chunk_id": pl.get("chunk_id"),
        "document_id": pl.get("document_id"),
        "external_id": parse_external_id(pl.get("filename")),
        "filename": pl.get("filename"),
        "name": pl.get("name"),
        "source": pl.get("source"),
        "source_type": pl.get("source_type"),
        "rol_number": _nullify(pl.get("rol_number")),
        "bcn_id_norm": _nullify(pl.get("bcn_id_norm")),
        "instance_name": _nullify(pl.get("instance_name")),
        "court_specific_name": _nullify(pl.get("court_specific_name")),
        "date": pl.get("date") or None,
        "publication_date": pl.get("publication_date") or None,
        "url": pl.get("url"),
        "content": content,
        "char_length": len(content),
    }


def pass_metadata(os_client, q_client, limit: int | None) -> None:
    print("\n[pase: metadata] scroll Qdrant -> bulk INDEX")
    total = q_client.count(collection_name=config.QDRANT_COLLECTION).count
    if limit is not None:
        total = min(total, limit)
    print(f"  total Qdrant: {total:,}")

    def _actions():
        offset = None
        yielded = 0
        while True:
            resp, offset = q_client.scroll(
                collection_name=config.QDRANT_COLLECTION,
                limit=config.BATCH_SIZE,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            if not resp:
                break
            for point in resp:
                if limit is not None and yielded >= limit:
                    return
                doc = _metadata_doc_from_point(point)
                yield {
                    "_op_type": "update",
                    "_index": config.INDEX_CHUNKS,
                    "_id": doc["chunk_uuid"],
                    "doc": doc,
                    "doc_as_upsert": True,
                }
                yielded += 1
            if offset is None:
                break

    _bulk(os_client, _actions(), desc="metadata", total=total)


# --- Pase: BM25 tokens (3 variantes) -----------------------------------------


def pass_bm25(os_client, preproc: str, limit: int | None) -> None:
    """preproc en {p1, p2, p3}. Lee c0X_pY_bm25_tokens.json y actualiza
    content_pX con los tokens joinados con espacio."""
    key = f"bm25_{preproc}"
    fname = config.VECTOR_FILES[key]
    path = Path(config.VECTORS_DIR) / fname
    field = f"content_{preproc}"

    print(f"\n[pase: {preproc}_bm25] {fname} -> UPDATE {field}")
    print(f"  loader: {_JSON_BACKEND}")
    t0 = time.time()
    raw = _load_json_file(path)
    chunk_ids = raw.get("ids") or []
    chunk_tokens = raw.get("tokens") or []
    print(f"  parseado en {time.time()-t0:.1f}s — {len(chunk_ids):,} entradas")

    if limit is not None:
        chunk_ids = chunk_ids[:limit]
        chunk_tokens = chunk_tokens[:limit]

    _bulk(
        os_client,
        _iter_bm25_updates(chunk_ids, chunk_tokens, field),
        desc=f"{preproc}_bm25",
        total=len(chunk_ids),
    )

    # Liberar memoria antes del siguiente pase.
    del raw, chunk_ids, chunk_tokens
    gc.collect()


# --- Pases: rank_features (TF-IDF y SPLADE) ----------------------------------


def _pass_rank_features(
    os_client, file_key: str, field: str, label: str, limit: int | None
) -> None:
    """Pase genérico para archivos de la forma:
        [{chunk_id, method, n_nonzero, vector: {token: peso}}, ...]
    Aplica a TF-IDF y a SPLADE (formato idéntico)."""
    fname = config.VECTOR_FILES[file_key]
    path = Path(config.VECTORS_DIR) / fname

    print(f"\n[pase: {label}] {fname} -> UPDATE {field}")
    print(f"  loader: {_JSON_BACKEND}")
    t0 = time.time()
    entries = _load_json_file(path)
    print(f"  parseado en {time.time()-t0:.1f}s — {len(entries):,} entradas")

    if limit is not None:
        entries = entries[:limit]

    _bulk(os_client, _iter_rank_feature_updates(entries, field), desc=label, total=len(entries))

    del entries
    gc.collect()


def pass_tfidf(os_client, preproc: str, limit: int | None) -> None:
    """preproc en {p1, p2, p3}. Lee c0X_pY_tfidf.json y actualiza tfidf_pX."""
    _pass_rank_features(
        os_client,
        file_key=f"tfidf_{preproc}",
        field=f"tfidf_{preproc}",
        label=f"{preproc}_tfidf",
        limit=limit,
    )


def pass_splade(os_client, preproc: str, limit: int | None) -> None:
    """preproc actualmente solo p1. Lee c07_p1_splade.json y actualiza splade_p1."""
    _pass_rank_features(
        os_client,
        file_key=f"splade_{preproc}",
        field=f"splade_{preproc}",
        label=f"{preproc}_splade",
        limit=limit,
    )


def pass_baseline_qdrant_bm25(os_client, limit: int | None) -> None:
    """Baseline BM25 extraído de la instancia Qdrant del cliente.

    Lee `baseline_qdrant_bm25.json` (vectores fastembed `Qdrant/bm25` con
    claves MurmurHash3) y actualiza el campo `baseline_qdrant_bm25`. El
    formato del archivo es el mismo que TF-IDF y SPLADE
    ([{chunk_id, method, n_nonzero, vector}, ...]) así que reusamos el
    pase genérico de rank_features.
    """
    _pass_rank_features(
        os_client,
        file_key="baseline_qdrant_bm25",
        field="baseline_qdrant_bm25",
        label="baseline_qdrant_bm25",
        limit=limit,
    )


# --- Main --------------------------------------------------------------------

PASSES = (
    "metadata",
    "p1_bm25",
    "p2_bm25",
    "p3_bm25",
    "p1_tfidf",
    "p2_tfidf",
    "p3_tfidf",
    "p1_splade",
    "baseline_qdrant_bm25",
)


def main(which: str, limit: int | None) -> None:
    os_client = clients.get_opensearch()

    if not os_client.indices.exists(index=config.INDEX_CHUNKS):
        print(f"[x] el índice {config.INDEX_CHUNKS} no existe.")
        print("    ejecute primero: python scripts/create_index.py --force")
        sys.exit(1)

    if not Path(config.VECTORS_DIR).is_dir() and which != "metadata":
        print(f"[x] no encuentro la carpeta {config.VECTORS_DIR}")
        sys.exit(1)

    if which == "all":
        # Conexión a Qdrant solo para metadata.
        q_client = clients.get_qdrant()
        pass_metadata(os_client, q_client, limit)
        for p in ("p1", "p2", "p3"):
            pass_bm25(os_client, p, limit)
        for p in ("p1", "p2", "p3"):
            pass_tfidf(os_client, p, limit)
        # SPLADE: por ahora solo p1.
        pass_splade(os_client, "p1", limit)
        # Baseline Qdrant BM25 (vectores extraídos del Qdrant del cliente).
        pass_baseline_qdrant_bm25(os_client, limit)
    elif which == "metadata":
        q_client = clients.get_qdrant()
        pass_metadata(os_client, q_client, limit)
    elif which == "baseline_qdrant_bm25":
        # Antes que la rama `endswith("_bm25")` porque también termina en _bm25.
        pass_baseline_qdrant_bm25(os_client, limit)
    elif which.endswith("_bm25"):
        pass_bm25(os_client, which.split("_")[0], limit)
    elif which.endswith("_tfidf"):
        pass_tfidf(os_client, which.split("_")[0], limit)
    elif which.endswith("_splade"):
        pass_splade(os_client, which.split("_")[0], limit)
    else:
        print(f"[x] pase desconocido: {which!r}. Opciones: {('all',) + PASSES}")
        sys.exit(1)

    os_client.indices.refresh(index=config.INDEX_CHUNKS)
    final = os_client.count(index=config.INDEX_CHUNKS)["count"]
    print(f"\n[final] total docs en {config.INDEX_CHUNKS}: {final:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pass",
        dest="which",
        choices=("all",) + PASSES,
        default="all",
        help="qué pase correr (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cantidad máxima de chunks a procesar por pase (útil para pruebas)",
    )
    args = parser.parse_args()
    main(which=args.which, limit=args.limit)
