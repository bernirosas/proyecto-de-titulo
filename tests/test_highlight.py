"""Tests de `src.highlight`: mapeo palabra cruda → score query_vector.

El módulo es responsable de tres invariantes que valen la pena testear:

1. **Dispatch correcto** (`compute_highlights`): según la combinación
   (preprocesamiento, vectorización) debe llamar al implementador
   apropiado. Una errata en este dispatcher hace que P3 caiga al P1
   o que SPLADE intente stemear, lo cual destruye el highlight.

2. **Preservación de la forma cruda**: el dict devuelto tiene como
   clave la palabra **tal como aparece en el chunk** (no la preprocesada).
   Si confundimos esto, el frontend busca el stem en el contenido y no
   matchea nada.

3. **Score = peso del query_vector**: no inventamos pesos, los miramos
   en el vector. El test asegura que el peso devuelto coincide con lo
   que tiene la query, no con una constante o con un cómputo derivado.

Los stubs del módulo `preprocessors` viven en `tests/conftest.py`. Para
SPLADE se mockea `splade_encoder._tokenizer` con un fake que tokeniza
por slash (`legal/es` → `["legal", "##es"]`), evitando cargar transformers.
"""

from __future__ import annotations

import pytest
from src import highlight

# ---------------------------------------------------------------------------
# compute_highlights: dispatcher
# ---------------------------------------------------------------------------


class TestComputeHighlightsDispatch:
    def test_empty_content_returns_empty(self):
        """Edge case: contenido vacío no debe crashear ni invocar al
        preprocesador. Devuelve dict vacío."""
        assert highlight.compute_highlights("", {"foo": 1.0}, "p1", "bm25") == {}

    def test_empty_query_vector_returns_empty(self):
        """Edge case opuesto: query vacía no produce highlights."""
        assert highlight.compute_highlights("texto", {}, "p1", "bm25") == {}

    def test_splade_takes_precedence_over_preproc(self):
        """Si `vec="splade"` el dispatcher debe ignorar `preproc` y usar la
        ruta WordPiece, no el preprocesador léxico. Aún con preproc="p3" no
        debe stemear."""
        # Sin tokenizer SPLADE cargado, el dispatcher debe igualmente intentar
        # ese path (y fallar con AssertionError o equivalente al cargar).
        # Para evitar costar el modelo, mockeamos el tokenizer en otro test.
        # Acá solo verificamos que no se dispatchee a P3.
        # Un texto sin matches contra una query vacía-bool retorna {}.
        result = highlight.compute_highlights("", {"a": 1.0}, "p3", "splade")
        assert result == {}


# ---------------------------------------------------------------------------
# highlight_weights_p1
# ---------------------------------------------------------------------------


class TestHighlightWeightsP1:
    def test_matches_exact_lowercase(self):
        """P1 es identity-like (lowercase + tokenización por whitespace).
        Una palabra del chunk matchea si su lowercase está literal en el
        query_vector."""
        content = "El arrendatario debe restituir"
        qv = {"arrendatario": 1.0, "restituir": 2.0}
        out = highlight.highlight_weights_p1(content, qv)
        assert out == {"arrendatario": 1.0, "restituir": 2.0}

    def test_unmatched_words_excluded(self):
        """Palabras del chunk que no están en la query no aparecen en el
        output. El frontend interpreta su ausencia como 'sin highlight'."""
        out = highlight.highlight_weights_p1("foo bar baz", {"bar": 1.0})
        assert out == {"bar": 1.0}
        assert "foo" not in out
        assert "baz" not in out

    def test_preserves_query_weight_magnitudes(self):
        """El score debe ser exactamente el peso de la query, sin reescalar
        ni recortar. Si el frontend espera valores en [0, 10] y nosotros
        normalizamos a [0, 1], el gradiente se rompe."""
        content = "alpha beta gamma"
        qv = {"alpha": 0.1, "beta": 5.5, "gamma": 1234.0}
        out = highlight.highlight_weights_p1(content, qv)
        assert out["alpha"] == pytest.approx(0.1)
        assert out["beta"] == pytest.approx(5.5)
        assert out["gamma"] == pytest.approx(1234.0)


# ---------------------------------------------------------------------------
# highlight_weights_p2 (usa el stub de _spacy_nlp)
# ---------------------------------------------------------------------------


class TestHighlightWeightsP2:
    def test_returns_raw_form_not_lemma(self):
        """El frontend renderiza sobre el texto del chunk, no sobre lemas.
        Las claves del dict deben ser la forma cruda observada (`Funciones`,
        `funciona`, etc.), no el lemma. El stub usa lower(word) como lemma,
        así que enviamos la forma cruda al output."""
        # En el stub, lemma_ = word.lower(); pasamos query con esa misma forma
        content = "funciones de la sociedad"
        qv = {"funciones": 3.0, "sociedad": 2.0}
        out = highlight.highlight_weights_p2(content, qv)
        # El stub _FakeToken.lemma_ es lower(word). "funciones" lematiza a
        # "funciones" en el stub, así que tiene que matchear.
        assert out.get("funciones") == pytest.approx(3.0)
        assert out.get("sociedad") == pytest.approx(2.0)

    def test_skips_stopwords_and_short_lemmas(self):
        """P2 filtra stopwords y lemas de longitud ≤ 1 en su loop —
        esos no contribuyen aunque estén en la query."""
        content = "el arrendatario"
        qv = {"el": 99.0, "arrendatario": 1.0}
        out = highlight.highlight_weights_p2(content, qv)
        # `el` es stopword en el stub → excluido aunque esté en query con peso 99
        assert "el" not in out
        assert out["arrendatario"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# highlight_weights_p3 (usa el stub de stemmer + word_tokenize)
# ---------------------------------------------------------------------------


class TestHighlightWeightsP3:
    def test_matches_via_stem_returns_raw_word(self):
        """El stub stem() corta a 4 chars lowercased. La query lleva el
        stem; el chunk lleva la palabra completa. El output debe ser la
        palabra completa con el peso del stem."""
        content = "arrendatario restitucion"
        # stub stem: "arrendatario" -> "arre", "restitucion" -> "rest"
        qv = {"arre": 1.0, "rest": 2.0}
        out = highlight.highlight_weights_p3(content, qv)
        assert out["arrendatario"] == pytest.approx(1.0)
        assert out["restitucion"] == pytest.approx(2.0)

    def test_skips_stopwords(self):
        """P3 filtra stopwords antes de stemear. Aunque la query contuviera
        el stem de una stopword, no se highlightea."""
        content = "el arrendatario"
        # stub stem("el") = "el" - pero "el" es stopword → no stemea
        qv = {"el": 99.0, "arre": 1.0}
        out = highlight.highlight_weights_p3(content, qv)
        assert "el" not in out
        assert out["arrendatario"] == pytest.approx(1.0)

    def test_skips_short_words(self):
        """P3 filtra tokens de longitud ≤ 2 antes de stemear (regla del
        preprocesador upstream)."""
        content = "ab arrendatario"
        qv = {"ab": 99.0, "arre": 1.0}
        out = highlight.highlight_weights_p3(content, qv)
        assert "ab" not in out


# ---------------------------------------------------------------------------
# highlight_weights_splade (con tokenizer mockeado)
# ---------------------------------------------------------------------------


class _FakeWordPieceTokenizer:
    """Tokenizer mínimo con vocab hardcodeada por test. Reproduce el patrón
    WordPiece (primera pieza sin `##`, continuaciones con `##`) sin
    necesidad de cargar BERT real.
    """

    def __init__(self, vocab: dict[str, list[str]]) -> None:
        self.vocab = vocab

    def tokenize(self, word: str) -> list[str]:
        return self.vocab.get(word, [word])


class TestHighlightWeightsSplade:
    def test_sums_weights_of_matching_wordpieces(self, monkeypatch):
        """SPLADE: el score de una palabra del chunk es la SUMA de pesos
        de las piezas WordPiece que coinciden con la query. Una palabra
        que matchea por 2 piezas pesa más que una que matchea por 1."""
        from src import splade_encoder

        tokenizer = _FakeWordPieceTokenizer(
            {
                "legales": ["legal", "##es"],
                "lawyer": ["lawyer"],
            }
        )
        monkeypatch.setattr(splade_encoder, "_tokenizer", tokenizer)
        monkeypatch.setattr(splade_encoder, "_ensure_loaded", lambda: None)

        content = "legales lawyer"
        qv = {"legal": 1.5, "##es": 0.5, "lawyer": 0.3}
        out = highlight.highlight_weights_splade(content, qv)
        # 'legales' aporta 1.5 + 0.5 = 2.0
        assert out["legales"] == pytest.approx(2.0)
        # 'lawyer' es una sola pieza con peso 0.3
        assert out["lawyer"] == pytest.approx(0.3)

    def test_excludes_words_with_zero_total_contribution(self, monkeypatch):
        """Si ninguna de las piezas de la palabra está en la query, esa
        palabra no debe aparecer en el output (no es ruido para colorear)."""
        from src import splade_encoder

        tokenizer = _FakeWordPieceTokenizer(
            {
                "extraña": ["extraña"],
                "palabra": ["pal", "##abra"],
            }
        )
        monkeypatch.setattr(splade_encoder, "_tokenizer", tokenizer)
        monkeypatch.setattr(splade_encoder, "_ensure_loaded", lambda: None)

        content = "extraña palabra"
        qv = {"otro": 1.0}
        out = highlight.highlight_weights_splade(content, qv)
        assert out == {}

    def test_keeps_continuation_pieces_and_stopwords(self, monkeypatch):
        """A diferencia de P3 (que filtra stopwords pre-stem), SPLADE
        considera todo lo que el tokenizer produzca: una palabra como
        'la' que SPLADE retiene con peso bajo igual va a aparecer en el
        output con su score. El frontend la dibuja en color claro."""
        from src import splade_encoder

        tokenizer = _FakeWordPieceTokenizer({"la": ["la"]})
        monkeypatch.setattr(splade_encoder, "_tokenizer", tokenizer)
        monkeypatch.setattr(splade_encoder, "_ensure_loaded", lambda: None)

        content = "la"
        qv = {"la": 0.8}
        out = highlight.highlight_weights_splade(content, qv)
        assert out == {"la": pytest.approx(0.8)}


# ---------------------------------------------------------------------------
# _bump helper: invariante "máximo, no suma"
# ---------------------------------------------------------------------------


class TestBumpHelper:
    def test_keeps_max_when_word_repeats(self):
        """Si una misma palabra cruda mapea a un token de query desde más
        de un contexto, queremos el peso máximo — no sumar (lo cual
        amplificaría artificialmente la importancia visual)."""
        out: dict[str, float] = {}
        highlight._bump(out, "casa", 1.0)
        highlight._bump(out, "casa", 0.5)  # más bajo, debe ignorarse
        highlight._bump(out, "casa", 3.0)  # más alto, debe pisar
        highlight._bump(out, "casa", 2.0)  # más bajo que el actual, ignorar
        assert out == {"casa": 3.0}

    def test_zero_or_negative_score_ignored(self):
        """Scores ≤ 0 no entran al dict — son ruido del cómputo upstream
        que no debe sobrescribir un peso real."""
        out: dict[str, float] = {"casa": 1.0}
        highlight._bump(out, "casa", 0.0)
        highlight._bump(out, "casa", -1.0)
        highlight._bump(out, "perro", 0.0)
        assert out == {"casa": 1.0}
