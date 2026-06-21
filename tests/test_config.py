"""Tests de consistencia del catálogo de técnicas.

El objetivo es detectar de inmediato situaciones en las que se agrega una
técnica al catálogo pero se olvida declarar su archivo en VECTOR_FILES o
viceversa: sin estos tests, el error solo aparecería en runtime al ingestar.

Se eliminaron dos tests previos por ser de bajo valor:

  - `test_splade_config_present` solo verificaba que dos constantes
    existieran (valor mínimo del 0% del tiempo de ingeniería).
  - `test_index_chunks_name` comparaba una constante consigo misma; si
    se renombra, el test se renombra con ella.
"""

from __future__ import annotations

import re

from src import config

VALID_PREPROCS = {"p1", "p2", "p3"}
VALID_VECS = {"bm25", "tfidf", "splade"}

# Técnicas que no siguen la convención pX_<vec>. Se documentan explícitamente
# como excepciones para que los tests de formato las salten sin debilitar
# la verificación del resto del catálogo.
#
# Cada una vive en su propio camino de ramificación dentro de
# `search.search()`:
#   - `baseline_qdrant_bm25`: vectores importados del Qdrant del cliente;
#      su clave en VECTOR_FILES coincide con el nombre de la técnica.
#   - `hybrid_rrf`: no tiene vectores propios — compone los de un sparse
#      partner con el ranking denso de Qdrant. Se excluye de VECTOR_FILES
#      adrede; el test de cobertura de archivos lo brinca explícitamente.
NON_CANONICAL_TECHNIQUES = {"baseline_qdrant_bm25", "hybrid_rrf"}
NON_CANONICAL_WITH_VECTOR_FILE = {"baseline_qdrant_bm25"}


def test_each_technique_has_well_formed_id():
    """Cada técnica canónica debe tener formato `pX_<vec>` con preproc y vec
    pertenecientes a los conjuntos válidos. Las técnicas registradas en
    `NON_CANONICAL_TECHNIQUES` se saltan adrede."""
    for method in config.TECHNIQUES:
        if method in NON_CANONICAL_TECHNIQUES:
            continue
        parts = method.split("_", 1)
        assert len(parts) == 2, f"{method!r} no tiene formato pX_<vec>"
        preproc, vec = parts
        assert preproc in VALID_PREPROCS, f"preproc inválido en {method!r}"
        assert vec in VALID_VECS, f"vectorizer inválido en {method!r}"


def test_techniques_are_unique():
    """No debe haber técnicas duplicadas en el catálogo."""
    assert len(config.TECHNIQUES) == len(set(config.TECHNIQUES))


def test_each_technique_has_corresponding_vector_file():
    """Falla diagnóstica más importante de la suite: para cada técnica
    `pX_vec` declarada debe existir VECTOR_FILES['vec_pX']. Las técnicas
    no-canónicas con vectores propios (p. ej. baseline_qdrant_bm25) usan
    el mismo string como clave; las que no tienen vectores propios
    (hybrid_rrf) se brincan adrede."""
    for method in config.TECHNIQUES:
        if method in NON_CANONICAL_TECHNIQUES:
            if method in NON_CANONICAL_WITH_VECTOR_FILE:
                assert method in config.VECTOR_FILES, (
                    f"falta archivo de vectores para la técnica no-canónica {method!r}: "
                    f"esperado VECTOR_FILES[{method!r}]"
                )
            else:
                assert method not in config.VECTOR_FILES, (
                    f"técnica compositiva {method!r} no debería estar en VECTOR_FILES — "
                    "no tiene vectores propios."
                )
            continue
        preproc, vec = method.split("_", 1)
        key = f"{vec}_{preproc}"
        assert key in config.VECTOR_FILES, (
            f"falta archivo de vectores para la técnica {method!r}: "
            f"esperado VECTOR_FILES[{key!r}]"
        )


def test_vector_file_naming_convention():
    """Convención `c0X_pY_<vec>(_tokens)?.json` para los archivos generados
    por nuestra pipeline. Archivos importados de fuentes externas (p. ej.
    `baseline_qdrant_bm25.json`, extraído del Qdrant del cliente) quedan
    excentos: su clave coincide con la del NON_CANONICAL_TECHNIQUES."""
    pattern = re.compile(r"^c\d{2}_p\d_(tfidf|bm25_tokens|splade)\.json$")
    for key, fname in config.VECTOR_FILES.items():
        if key in NON_CANONICAL_TECHNIQUES:
            continue
        assert pattern.match(fname), (
            f"archivo {fname!r} (clave {key!r}) no sigue la convención " "c0X_pY_<vec>.json"
        )


def test_hybrid_rrf_config():
    """`hybrid_rrf` debe estar en TECHNIQUES, con constantes RRF razonables
    y sparse-partners válidos (todos miembros del catálogo sparse)."""
    assert "hybrid_rrf" in config.TECHNIQUES
    assert config.RRF_K == 60, "Constante k del paper de Cormack 2009"
    assert config.RRF_FETCH_MULTIPLIER >= 1
    assert config.RRF_FETCH_MIN >= 1
    assert config.DEFAULT_HYBRID_SPARSE in config.HYBRID_SPARSE_VARIANTS
    # Todos los partners deben ser técnicas sparse válidas (no se permite
    # `hybrid_rrf` como su propio partner — sería recursión infinita).
    sparse_only = set(config.TECHNIQUES) - {"hybrid_rrf"}
    for partner in config.HYBRID_SPARSE_VARIANTS:
        assert (
            partner in sparse_only
        ), f"sparse partner {partner!r} no está en el catálogo de técnicas sparse."


def test_benchmark_indices_declared():
    """Los índices operacionales del benchmark deben estar declarados como
    constantes en config.py para que no aparezcan strings hardcodeadas en
    los scripts."""
    assert config.INDEX_RETRIEVAL_RESULTS == "retrieval_results"
    # Los demás índices del benchmark (ground_truth) se declaran dentro de
    # scripts/benchmark/ porque su lifecycle es propio del pipeline de
    # evaluación, no del backend en producción.
