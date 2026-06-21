"""Configuración global de pytest.

Su trabajo principal: instalar un stub del módulo `preprocessors` (que vive
en `Vectorizacion/sparse-benchmark/src/preprocessors.py` y carga spaCy +
NLTK al importarse) ANTES de que cualquier test importe `src.preprocess_adapter`.

Sin este stub los tests requerirían instalar spaCy, descargar
`es_core_news_lg` (~560 MB) y bajar los datasets de NLTK para correr.
Como los tests son unitarios sobre la lógica del backend (no sobre los
preprocessadores en sí), esto es desproporcionado: el stub provee funciones
deterministas y livianas con la misma signatura que el upstream.
"""

from __future__ import annotations

import sys
from types import ModuleType


def _install_preprocessors_stub() -> None:
    """Inserta un módulo `preprocessors` falso en `sys.modules`.

    Cubre las funciones y atributos que `src.preprocess_adapter` importa
    desde el módulo upstream: clean_pdf_noise, preprocess_p1, preprocess_p3
    y `nlp` (instancia de spaCy).
    """
    if "preprocessors" in sys.modules:
        return

    fake = ModuleType("preprocessors")

    def clean_pdf_noise(text: str) -> str:
        if not text:
            return ""
        return text.replace("\xa0", " ").replace("​", "").strip()

    def preprocess_p1(text: str) -> list[str]:
        if not text:
            return []
        return [w.lower() for w in text.split() if w]

    def preprocess_p3(text: str) -> list[str]:
        # Stem trivial: primeros 4 caracteres en minúscula, descarta no alfa.
        if not text:
            return []
        return [w.lower()[:4] for w in text.split() if w.isalpha()]

    class _FakeToken:
        def __init__(self, word: str) -> None:
            self.text = word
            self.lemma_ = word.lower()
            self.is_stop = word.lower() in {"el", "la", "los", "las", "de", "y"}
            self.is_punct = word in {".", ",", ";", ":"}
            self.is_space = word.isspace()

    class _FakeNLP:
        def __call__(self, text: str) -> list[_FakeToken]:
            return [_FakeToken(w) for w in (text or "").split()]

    class _FakeStemmer:
        """Stub del Snowball stemmer: corta a 4 caracteres en minúscula.
        Suficiente para que `src.highlight` corra sin cargar NLTK."""

        def stem(self, word: str) -> str:
            return (word or "").lower()[:4]

    fake.clean_pdf_noise = clean_pdf_noise  # type: ignore[attr-defined]
    fake.preprocess_p1 = preprocess_p1  # type: ignore[attr-defined]
    fake.preprocess_p3 = preprocess_p3  # type: ignore[attr-defined]
    fake.nlp = _FakeNLP()  # type: ignore[attr-defined]
    fake.stemmer = _FakeStemmer()  # type: ignore[attr-defined]
    fake.stop_words = {  # type: ignore[attr-defined]
        "el",
        "la",
        "los",
        "las",
        "de",
        "y",
        "que",
        "a",
        "en",
        "un",
        "una",
    }

    sys.modules["preprocessors"] = fake


def _install_nltk_stub() -> None:
    """Stub mínimo de `nltk.tokenize.word_tokenize` para que `src.highlight`
    importe sin necesidad de tener NLTK instalado. Tokeniza por whitespace;
    suficiente para los tests unitarios sobre la lógica de highlights.
    """
    if "nltk.tokenize" in sys.modules:
        return

    nltk_mod = ModuleType("nltk")
    nltk_tokenize_mod = ModuleType("nltk.tokenize")

    def word_tokenize(text: str, language: str = "spanish") -> list[str]:
        del language  # presente para emparejar la firma de nltk; no se usa.
        return (text or "").split()

    nltk_tokenize_mod.word_tokenize = word_tokenize  # type: ignore[attr-defined]
    sys.modules.setdefault("nltk", nltk_mod)
    sys.modules["nltk.tokenize"] = nltk_tokenize_mod


def _install_genai_stub() -> None:
    import importlib

    if "google.genai" in sys.modules:
        return

    try:
        google_mod = importlib.import_module("google")
    except ImportError:
        google_mod = ModuleType("google")
        google_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["google"] = google_mod

    genai_mod = ModuleType("google.genai")
    types_mod = ModuleType("google.genai.types")

    class Client:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("stub genai.Client no debe instanciarse en tests")

    class EmbedContentConfig:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    genai_mod.Client = Client  # type: ignore[attr-defined]
    genai_mod.types = types_mod  # type: ignore[attr-defined]
    types_mod.EmbedContentConfig = EmbedContentConfig  # type: ignore[attr-defined]
    google_mod.genai = genai_mod  # type: ignore[attr-defined]

    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.types"] = types_mod


_install_preprocessors_stub()
_install_nltk_stub()
_install_genai_stub()
