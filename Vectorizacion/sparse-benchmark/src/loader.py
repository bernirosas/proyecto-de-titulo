"""
loader.py
─────────
Carga y valida los chunks desde out_payload.txt.
El archivo está en formato Python dict (no JSON válido),
por lo que se usa ast.literal_eval y NO json.loads.
"""

import ast
import logging

logger = logging.getLogger(__name__)


def load_chunks(filepath: str = "data/out_payload.txt") -> list[dict]:
    logger.info(f"Cargando chunks desde {filepath}...")

    chunks = []
    skipped = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = ast.literal_eval(line)
                text = item.get("content", "") or item.get("text", "")
                if text and text.strip():
                    chunks.append({
                        "id":   item.get("id") or item.get("chunk_id"),
                        "text": text,
                    })
                else:
                    skipped += 1
            except Exception as e:
                logger.warning(f"Línea {line_num} inválida: {e}")
                skipped += 1

    logger.info(f"Cargados {len(chunks)} chunks válidos — {skipped} omitidos")
    return chunks


def inspect_chunks(chunks: list[dict], n: int = 3) -> None:
    """
    Imprime una inspección rápida de los primeros n chunks.
    Útil para verificar que el formato es el esperado antes de procesar.
    """
    print(f"\nTotal chunks cargados: {len(chunks)}")
    print(f"Campos disponibles: {list(chunks[0].keys())}")
    print()

    for i, chunk in enumerate(chunks[:n]):
        print(f"--- Chunk {i} ---")
        print(f"ID:    {chunk['id']}")
        print(f"Texto: {chunk['text'][:200]}...")
        print()
