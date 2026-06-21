from __future__ import annotations

import pytest
from src import config, gemini_embed


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeResponse:
    def __init__(self, vectors):
        self.embeddings = [_FakeEmbedding(v) for v in vectors]


class _FakeModels:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.models = _FakeModels(response=response, error=error)


@pytest.fixture
def patch_client(monkeypatch):
    def _install(response=None, error=None):
        client = _FakeClient(response=response, error=error)
        monkeypatch.setattr(gemini_embed, "get_gemini_client", lambda: client)
        return client

    return _install


def test_embed_query_returns_vector(patch_client):
    vector = [0.1] * config.DENSE_DIM
    client = patch_client(response=_FakeResponse([vector]))

    result = gemini_embed.embed_query("  obligaciones del arrendador  ")

    assert result == vector
    assert client.models.calls[0]["contents"] == ["obligaciones del arrendador"]
    assert client.models.calls[0]["model"] == config.GEMINI_EMBED_MODEL


def test_embed_query_rejects_empty(patch_client):
    patch_client(response=_FakeResponse([[0.0] * config.DENSE_DIM]))
    with pytest.raises(ValueError):
        gemini_embed.embed_query("   ")


def test_embed_query_rejects_too_long(patch_client):
    patch_client(response=_FakeResponse([[0.0] * config.DENSE_DIM]))
    with pytest.raises(ValueError):
        gemini_embed.embed_query("x" * (config.LIVE_QUERY_MAX_CHARS + 1))


def test_embed_query_rejects_wrong_dimension(patch_client):
    patch_client(response=_FakeResponse([[0.0, 0.1, 0.2]]))
    with pytest.raises(gemini_embed.GeminiEmbedError):
        gemini_embed.embed_query("consulta")


def test_embed_query_wraps_api_error(patch_client):
    patch_client(error=RuntimeError("quota exceeded"))
    with pytest.raises(gemini_embed.GeminiEmbedError):
        gemini_embed.embed_query("consulta")


def test_embed_query_raises_on_empty_embeddings(patch_client):
    patch_client(response=_FakeResponse([]))
    with pytest.raises(gemini_embed.GeminiEmbedError):
        gemini_embed.embed_query("consulta")
