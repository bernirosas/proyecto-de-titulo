from __future__ import annotations

import json

import pytest
from src import config, dense_qdrant


@pytest.fixture
def live_cache_file(tmp_path, monkeypatch):
    path = tmp_path / "live_cache.json"
    monkeypatch.setattr(config, "LIVE_DENSE_CACHE_PATH", str(path))
    monkeypatch.setattr(config, "HYBRID_LIVE_EMBED_ENABLED", True)
    monkeypatch.setattr(dense_qdrant, "_LIVE_CACHE", None)
    return path


@pytest.fixture
def counting_embed(monkeypatch):
    calls = []

    def fake_embed(text):
        calls.append(text)
        return [float(len(calls))] * config.DENSE_DIM

    monkeypatch.setattr("src.gemini_embed.embed_query", fake_embed)
    return calls


def test_precomputed_path_skips_embedding(monkeypatch, live_cache_file):
    monkeypatch.setattr(dense_qdrant, "get_query_vector", lambda qid: [0.5] * config.DENSE_DIM)

    def explode(_text):
        raise AssertionError("no debe embeber cuando hay query_id")

    monkeypatch.setattr("src.gemini_embed.embed_query", explode)

    vector, source = dense_qdrant.get_or_embed_query_vector("texto", query_id="q001")

    assert source == "precomputed"
    assert vector == [0.5] * config.DENSE_DIM


def test_live_miss_embeds_once_and_persists(live_cache_file, counting_embed):
    vector, source = dense_qdrant.get_or_embed_query_vector("arriendo de inmueble")

    assert source == "live"
    assert len(vector) == config.DENSE_DIM
    assert len(counting_embed) == 1
    assert live_cache_file.exists()

    stored = json.loads(live_cache_file.read_text(encoding="utf-8"))
    entry = next(iter(stored.values()))
    assert entry["text"] == "arriendo de inmueble"
    assert entry["vector"] == vector


def test_live_hit_in_memory_does_not_reembed(live_cache_file, counting_embed):
    dense_qdrant.get_or_embed_query_vector("misma query")
    dense_qdrant.get_or_embed_query_vector("  MISMA   query ")

    assert len(counting_embed) == 1


def test_live_hit_from_disk_after_reload(live_cache_file, counting_embed, monkeypatch):
    first, _ = dense_qdrant.get_or_embed_query_vector("persiste esto")
    assert len(counting_embed) == 1

    monkeypatch.setattr(dense_qdrant, "_LIVE_CACHE", None)

    def explode(_text):
        raise AssertionError("debió leer del disco, no re-embeber")

    monkeypatch.setattr("src.gemini_embed.embed_query", explode)

    second, source = dense_qdrant.get_or_embed_query_vector("persiste esto")

    assert source == "live"
    assert second == first


def test_disabled_flag_rejects_live(live_cache_file, monkeypatch):
    monkeypatch.setattr(config, "HYBRID_LIVE_EMBED_ENABLED", False)
    with pytest.raises(ValueError):
        dense_qdrant.get_or_embed_query_vector("cualquier cosa")


def test_empty_query_rejected(live_cache_file):
    with pytest.raises(ValueError):
        dense_qdrant.get_or_embed_query_vector("   ")
