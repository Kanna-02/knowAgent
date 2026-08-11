from __future__ import annotations

import json

import httpx
import pytest

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.infrastructure.http_rerank import HttpRerankProvider


@pytest.mark.anyio
async def test_rerank_validates_and_returns_ranked_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://model-service:8100/v1/rerank"
        assert json.loads(request.content) == {
            "model": "BAAI/bge-reranker-v2-m3",
            "query": "如何部署？",
            "documents": ["先迁移数据库", "重启服务"],
            "top_k": 2,
        }
        return httpx.Response(
            200,
            json={
                "model": "BAAI/bge-reranker-v2-m3",
                "model_version": "revision-1",
                "results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.2}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpRerankProvider(
            base_url="http://model-service:8100/v1",
            model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=5,
            client=client,
        )
        result = await provider.rerank(
            query="如何部署？",
            documents=("先迁移数据库", "重启服务"),
            top_k=2,
        )

    assert result.model_version == "revision-1"
    assert [(item.index, item.score) for item in result.results] == [(1, 0.9), (0, 0.2)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "results",
    [
        [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.2}],
        [{"index": 0, "score": 0.9}, {"index": 0, "score": 0.2}],
        [{"index": 0, "score": 0.9}],
    ],
)
async def test_rerank_rejects_invalid_result_contract(results: list[dict[str, float]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "model": "BAAI/bge-reranker-v2-m3",
                "model_version": "revision-1",
                "results": results,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpRerankProvider(
            base_url="http://model-service:8100/v1",
            model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=5,
            client=client,
        )
        with pytest.raises(ProviderUnavailableError):
            await provider.rerank(
                query="如何部署？",
                documents=("先迁移数据库", "重启服务"),
                top_k=2,
            )


@pytest.mark.anyio
async def test_rerank_validates_request_before_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpRerankProvider(
            base_url="http://model-service:8100/v1",
            model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=5,
            client=client,
        )
        with pytest.raises(ValidationError, match="重排"):
            await provider.rerank(query="  ", documents=("文档",), top_k=1)


@pytest.mark.anyio
async def test_rerank_skips_repeated_requests_during_failure_cooldown() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        del request
        requests += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = HttpRerankProvider(
            base_url="http://model-service:8100/v1",
            model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=5,
            failure_cooldown_seconds=60,
            client=client,
        )
        for _ in range(2):
            with pytest.raises(ProviderUnavailableError):
                await provider.rerank(query="如何部署？", documents=("文档",), top_k=1)

    assert requests == 1
