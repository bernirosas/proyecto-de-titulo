"""Crea el índice chunks_maqui en OpenSearch.

Uso:
    python scripts/create_index.py           # crea si no existe
    python scripts/create_index.py --force   # borra y recrea
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from src import clients, config, schema


def main(force: bool = False) -> None:
    c = clients.get_opensearch()

    if c.indices.exists(index=config.INDEX_CHUNKS):
        if force:
            print(f"[!] borrando índice existente {config.INDEX_CHUNKS}")
            c.indices.delete(index=config.INDEX_CHUNKS)
        else:
            print(f"[=] {config.INDEX_CHUNKS} ya existe, nada que hacer")
            print("    usá --force para borrar y recrear")
            return

    c.indices.create(index=config.INDEX_CHUNKS, body=schema.CHUNKS_MAPPING)
    print(f"[+] creado {config.INDEX_CHUNKS}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true", help="borra el índice si ya existe y lo vuelve a crear"
    )
    args = parser.parse_args()
    main(force=args.force)
