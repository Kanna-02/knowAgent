from __future__ import annotations

import json

import httpx
import pytest

from knowagent.common.errors import ProviderUnavailableError
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider


@pytest.mark.asyncio
async def test_embed_validates_and_returns_model_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://model-service:8100/v1/embeddings"
        assert json.loads(request.content) == {"model": "bge-m3", "texts": ["问题"]}
        return httpx.Response(
            200,
            json={
                "model": "bge-m3",
                "model_version": "2026-08",
                "dimension": 3,
                "normalized": True,
                "vectors": [[0.1, 0.2, 0.3]],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpEmbeddingProvider(
            base_url="http://model-service:8100/v1",
            model="bge-m3",
            timeout_seconds=15,
            client=client,
        )
        result = await provider.embed(texts=("问题",))

    assert result.model == "bge-m3"
    assert result.model_version == "2026-08"
    assert result.vectors == ((0.1, 0.2, 0.3),)


@pytest.mark.asyncio
async def test_embed_rejects_response_count_or_dimension_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "model": "bge-m3",
                "model_version": "2026-08",
                "dimension": 2,
                "normalized": True,
                "vectors": [[0.1, 0.2, 0.3]],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpEmbeddingProvider(
            base_url="http://model-service:8100/v1",
            model="bge-m3",
            timeout_seconds=15,
            client=client,
        )
        with pytest.raises(ProviderUnavailableError):
            await provider.embed(texts=("问题",))


@pytest.mark.asyncio
async def test_embed_maps_network_and_http_errors_to_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, text="internal details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpEmbeddingProvider(
            base_url="http://model-service:8100/v1",
            model="bge-m3",
            timeout_seconds=15,
            client=client,
        )
        with pytest.raises(ProviderUnavailableError) as captured:
            await provider.embed(texts=("问题",))

    assert "internal details" not in str(captured.value)
