from __future__ import annotations

import asyncio
import math
import os

import httpx
import pytest

from knowagent_model.ollama import OllamaEmbeddingConfig, OllamaEmbeddingService


@pytest.mark.integration
def test_live_ollama_embedding_contract() -> None:
    base_url = os.getenv("KNOWAGENT_TEST_OLLAMA_BASE_URL", "").strip()
    expected_digest = os.getenv("KNOWAGENT_TEST_OLLAMA_MODEL_DIGEST", "").strip()
    if not base_url or not expected_digest:
        pytest.skip("live Ollama endpoint and expected digest are not configured")

    model = os.getenv("KNOWAGENT_TEST_OLLAMA_MODEL", "bge-m3").strip()
    model_version = os.getenv(
        "KNOWAGENT_TEST_OLLAMA_MODEL_VERSION", f"ollama-{model}-{expected_digest}"
    ).strip()
    dimension = int(os.getenv("KNOWAGENT_TEST_OLLAMA_DIMENSION", "1024"))

    async def scenario() -> None:
        async with httpx.AsyncClient(timeout=300.0) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=OllamaEmbeddingConfig(
                    base_url=base_url,
                    model=model,
                    model_version=model_version,
                    expected_digest=expected_digest,
                    dimension=dimension,
                    request_batch_size=1,
                    max_concurrency=1,
                    keep_alive="5m",
                    health_timeout_seconds=5.0,
                ),
            )
            assert await service.ready() is True
            result = await service.embed(model=model, texts=("KnowAgent 集成测试",))

        assert result.model == model
        assert result.model_version == model_version
        assert result.dimension == dimension
        assert result.normalized is True
        assert len(result.vectors) == 1
        assert math.sqrt(sum(value * value for value in result.vectors[0])) == pytest.approx(1.0)

    asyncio.run(scenario())
