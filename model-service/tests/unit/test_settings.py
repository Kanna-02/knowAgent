from __future__ import annotations

from collections.abc import Callable

import pytest

from knowagent_model.settings import ModelServiceSettings


def test_settings_defaults_match_existing_local_bge_m3_volume() -> None:
    settings = ModelServiceSettings()

    assert settings.embedding_model == "bge-m3"
    assert settings.embedding_model_version == "ollama-bge-m3-79076464"
    assert settings.ollama_model_digest == "79076464"
    assert settings.embedding_dimension == 1024
    assert settings.ollama_batch_size == 4
    assert settings.ollama_max_concurrency == 1
    assert settings.ollama_timeout_seconds == 240.0
    assert settings.ollama_health_timeout_seconds == 5.0
    assert settings.ollama_keep_alive == "10m"
    assert settings.rerank_model == "BAAI/bge-reranker-v2-m3"
    assert settings.rerank_model_path is None
    assert settings.rerank_batch_size == 4
    assert settings.rerank_use_fp16 is False


def test_settings_loads_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWAGENT_MODEL_OLLAMA_BASE_URL", "http://ollama:11434/")
    monkeypatch.setenv("KNOWAGENT_MODEL_EMBEDDING_MODEL", "custom-model")
    monkeypatch.setenv("KNOWAGENT_MODEL_EMBEDDING_VERSION", "custom-model-abcdef12")
    monkeypatch.setenv("KNOWAGENT_MODEL_OLLAMA_MODEL_DIGEST", "abcdef12")
    monkeypatch.setenv("KNOWAGENT_MODEL_EMBEDDING_DIMENSION", "3")
    monkeypatch.setenv("KNOWAGENT_MODEL_OLLAMA_BATCH_SIZE", "2")
    monkeypatch.setenv("KNOWAGENT_MODEL_MAX_REQUEST_TEXTS", "4")
    monkeypatch.setenv("KNOWAGENT_MODEL_PORT", "8200")
    monkeypatch.setenv("KNOWAGENT_MODEL_OLLAMA_HEALTH_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_MODEL", "custom-reranker")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_MODEL_PATH", "/models/custom-reranker")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_MODEL_VERSION", "revision-1")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_BATCH_SIZE", "3")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_USE_FP16", "true")
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_DEVICE", "cuda:0")

    settings = ModelServiceSettings.from_environment()

    assert settings.ollama_base_url == "http://ollama:11434/"
    assert settings.embedding_model == "custom-model"
    assert settings.ollama_model_digest == "abcdef12"
    assert settings.embedding_dimension == 3
    assert settings.ollama_batch_size == 2
    assert settings.max_request_texts == 4
    assert settings.port == 8200
    assert settings.ollama_health_timeout_seconds == 2.5
    assert settings.rerank_model == "custom-reranker"
    assert settings.rerank_model_path == "/models/custom-reranker"
    assert settings.rerank_model_version == "revision-1"
    assert settings.rerank_batch_size == 3
    assert settings.rerank_use_fp16 is True
    assert settings.rerank_device == "cuda:0"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ModelServiceSettings(embedding_model=""),
        lambda: ModelServiceSettings(ollama_model_digest=""),
        lambda: ModelServiceSettings(ollama_model_digest="1234567"),
        lambda: ModelServiceSettings(ollama_model_digest="not-hex!!"),
        lambda: ModelServiceSettings(
            embedding_model_version="ollama-bge-m3-deadbeef",
            ollama_model_digest="daec91ff",
        ),
        lambda: ModelServiceSettings(embedding_dimension=0),
        lambda: ModelServiceSettings(ollama_health_timeout_seconds=0),
        lambda: ModelServiceSettings(ollama_batch_size=3, max_request_texts=2),
        lambda: ModelServiceSettings(port=65_536),
        lambda: ModelServiceSettings(rerank_batch_size=0),
        lambda: ModelServiceSettings(rerank_device=" "),
        lambda: ModelServiceSettings(rerank_model_path=" "),
    ],
)
def test_settings_rejects_invalid_values(factory: Callable[[], ModelServiceSettings]) -> None:
    with pytest.raises(ValueError):
        factory()


def test_settings_rejects_invalid_rerank_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWAGENT_MODEL_RERANK_USE_FP16", "sometimes")

    with pytest.raises(ValueError, match="KNOWAGENT_MODEL_RERANK_USE_FP16"):
        ModelServiceSettings.from_environment()
