"""Ingesta el corpus Maqui desde Qdrant hacia el índice chunks_maqui de OpenSearch.

Hace scroll sobre la colección Qdrant en batches, transforma cada point al
documento OpenSearch según el mapping de schema.py, y bulk-indexa. Idempotente:
usa chunk_uuid como _id, por lo que reejecutarlo sobre el mismo set no duplica
documentos, solo los actualiza.

Uso:
    python scripts/ingest.py                # corre toda la ingestión
    python scripts/ingest.py --limit 1000   # solo para pruebas
    python scripts/ingest.py --dry-run      # no escribe, solo valida transform
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opensearchpy.helpers import streaming_bulk
from src import clients, config
from tqdm import tqdm

_EXTERNAL_ID_RE = re.compile(r"_(\d+)_")


def parse_external_id(filename: str | None) -> int | None:
    """Extrae el ID externo codificado en el filename.

    Ejemplos observados en el corpus:
        SII_19164_ROL_4-2023  -> 19164
        SII_1234_OFIC_5-2020  -> 1234

    Devuelve None si el filename no matchea el patrón `_<dígitos>_`.
    """
    if not filename:
        return None
    m = _EXTERNAL_ID_RE.search(filename)
    return int(m.group(1)) if m else None


def _nullify(value: Any) -> Any:
    """Convierte los marcadores de null usados por Qdrant ('' y 0) en None.

    Motivo: el censo del corpus mostró que campos como rol_number, bcn_id_norm,
    instance_name, court_specific_name usan "" o 0 para indicar ausencia.
    En OpenSearch preferimos None para que el campo quede genuinamente vacío.
    """
    if value == "" or value == 0:
        return None
    return value


def transform(point: Any) -> dict:
    """Mapea un point de Qdrant al documento OpenSearch según chunks_maqui."""
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


def _iter_actions(q_client, limit: int | None):
    """Generador que scrollea Qdrant y emite acciones bulk para OpenSearch."""
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
            yield {
                "_op_type": "index",
                "_index": config.INDEX_CHUNKS,
                "_id": str(point.id),
                "_source": transform(point),
            }
            yielded += 1
        if offset is None:
            break


def main(limit: int | None = None, dry_run: bool = False) -> None:
    os_client = clients.get_opensearch()
    q_client = clients.get_qdrant()

    if not os_client.indices.exists(index=config.INDEX_CHUNKS):
        print(f"[x] el índice {config.INDEX_CHUNKS} no existe.")
        print("    ejecute primero: python scripts/create_index.py")
        sys.exit(1)

    total = q_client.count(collection_name=config.QDRANT_COLLECTION).count
    if limit is not None:
        total = min(total, limit)
    print(f"total a indexar: {total}")

    if dry_run:
        print("[dry-run] validando transform sobre los primeros 3 points")
        offset = None
        resp, _ = q_client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            limit=3,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in resp:
            doc = transform(p)
            print(f"\n--- {doc['chunk_uuid']} ---")
            for k, v in doc.items():
                if k == "content":
                    v = (v or "")[:80].replace("\n", " ") + "..."
                print(f"  {k}: {v!r}")
        return

    pbar = tqdm(total=total, desc="ingestando", unit="chunk")
    indexed = 0
    failures = 0

    for success, info in streaming_bulk(
        os_client,
        _iter_actions(q_client, limit=limit),
        chunk_size=config.BATCH_SIZE,
        raise_on_error=False,
        raise_on_exception=False,
        yield_ok=True,
    ):
        pbar.update(1)
        if success:
            indexed += 1
        else:
            failures += 1
            if failures <= 3:
                print(f"\n[fail] {info}")

    pbar.close()
    os_client.indices.refresh(index=config.INDEX_CHUNKS)

    final_count = os_client.count(index=config.INDEX_CHUNKS)["count"]
    print(f"\nindexados ok: {indexed}")
    print(f"fallos:       {failures}")
    print(f"total en {config.INDEX_CHUNKS}: {final_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cantidad máxima de chunks a indexar (útil para pruebas)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="no escribe; imprime el transform de los primeros 3 points",
    )
    args = parser.parse_args()
    main(limit=args.limit, dry_run=args.dry_run)
