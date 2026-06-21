"""Corre `retrieve_for_query.main` sobre todas las queries en UN solo proceso.

A diferencia de iterar `docker compose run --rm` por cada query (que arranca
un contenedor nuevo y vuelve a cargar el encoder SPLADE y el ONNX de
fastembed cada vez), aquí abrimos UN proceso Python que mantiene los
encoders en memoria a partir de la primera invocación. Eso permite medir
la latencia warm de cada técnica — relevante para reportar lo que un
usuario en producción experimentaría a partir de la segunda query.

La primera query del run paga el cold-start completo (carga de modelos
+ I/O); las siguientes solo el retrieve propiamente tal. Si solo te
interesan las warm, ignora la latencia de la primera query del log o
ejecuta sobre una query "dummy" antes que las del benchmark.

Uso:
    docker compose run --rm app python scripts/benchmark/retrieve_all.py

Recomendado correrlo después de cambiar config (p.ej. tras ajustar el
`BASELINE_QDRANT_BM25_LANGUAGE`) para regenerar los pools con latencias
representativas SIN re-juzgar (los judgments son función del contenido
de los chunks, no de la latencia).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Mismo truco sys.path que retrieve_for_query.py: agrega la raíz del repo
# para que `from src import ...` resuelva.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from retrieve_for_query import main as retrieve_main  # noqa: E402


def main(queries_dir: Path, output_dir: Path, size: int, shuffle: bool, seed: int) -> None:
    query_files = sorted(queries_dir.glob("q*_*.json"))
    if not query_files:
        sys.exit(f"[x] no hay queries en {queries_dir}")

    print(f"[run-warm] procesando {len(query_files)} queries en UN proceso")
    print("           la primera paga cold-start; las siguientes son warm.")
    print()

    for i, qf in enumerate(query_files, 1):
        print("========================================")
        print(f"  [{i}/{len(query_files)}] {qf.name}")
        print("========================================")
        retrieve_main(
            query_file=qf,
            output_dir=output_dir,
            size=size,
            shuffle=shuffle,
            seed=seed,
        )
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--queries-dir", type=Path, default=Path("scripts/benchmark/queries"))
    parser.add_argument("--output-dir", type=Path, default=Path("scripts/benchmark/pools"))
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument("--no-shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    main(
        queries_dir=args.queries_dir,
        output_dir=args.output_dir,
        size=args.size,
        shuffle=not args.no_shuffle,
        seed=args.seed,
    )
