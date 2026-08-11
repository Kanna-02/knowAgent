from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from knowagent_model.app import create_app
from knowagent_model.embedding import EmbeddingBatch, EmbeddingServiceError
from knowagent_model.rerank import RerankBatch, RerankResult, RerankServiceError
from knowagent_model.settings import ModelServiceSettings


class StubEmbeddingService:
    def __init__(self, *, ready: bool = True, error: EmbeddingServiceError | None = None) -> None:
        self.is_ready = ready
        self.error = error
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def embed(self, *, model: str, texts: tuple[str, ...]) -> EmbeddingBatch:
        self.calls.append((model, texts))
        if self.error is not None:
            raise self.error
        return EmbeddingBatch(
            model=model,
            model_version="ollama-bge-m3-daec91ff",
            dimension=3,
            normalized=True,
            vectors=((0.6, 0.8, 0.0),),
        )

    async def ready(self) -> bool:
        return self.is_ready


class SlowEmbeddingService:
    def __init__(self) -> None:
        self.cancelled = False

    async def embed(self, *, model: str, texts: tuple[str, ...]) -> EmbeddingBatch:
        del model, texts
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("slow embedding unexpectedly completed")

    async def ready(self) -> bool:
        return True


class StubRerankService:
    def __init__(self, *, ready: bool = True, error: RerankServiceError | None = None) -> None:
        self.is_ready = ready
        self.error = error
        self.calls: list[tuple[str, str, tuple[str, ...], int]] = []

    async def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch:
        self.calls.append((model, query, documents, top_k))
        if self.error is not None:
            raise self.error
        return RerankBatch(
            model=model,
            model_version="revision-1",
            results=(RerankResult(index=1, score=0.9), RerankResult(index=0, score=0.2)),
        )

    async def ready(self) -> bool:
        return self.is_ready


def test_embeddings_endpoint_matches_backend_provider_contract() -> None:
    service = StubEmbeddingService()
    with TestClient(create_app(service=service)) as client:
        response = client.post("/v1/embeddings", json={"model": "bge-m3", "texts": ["问题"]})

    assert response.status_code == 200
    assert response.json() == {
        "model": "bge-m3",
        "model_version": "ollama-bge-m3-daec91ff",
        "dimension": 3,
        "normalized": True,
        "vectors": [[0.6, 0.8, 0.0]],
    }
    assert service.calls == [("bge-m3", ("问题",))]


def test_embeddings_endpoint_rejects_blank_text_before_provider_call() -> None:
    service = StubEmbeddingService()
    with TestClient(create_app(service=service)) as client:
        response = client.post("/v1/embeddings", json={"model": "bge-m3", "texts": ["   "]})

    assert response.status_code == 422
    assert service.calls == []


def test_embeddings_endpoint_enforces_batch_and_text_limits() -> None:
    service = StubEmbeddingService()
    settings = ModelServiceSettings(
        ollama_batch_size=1,
        max_request_texts=1,
        max_text_chars=3,
        max_total_text_chars=3,
    )
    with TestClient(create_app(service=service, settings=settings)) as client:
        batch_response = client.post(
            "/v1/embeddings", json={"model": "bge-m3", "texts": ["甲", "乙"]}
        )
        text_response = client.post(
            "/v1/embeddings", json={"model": "bge-m3", "texts": ["超过限制"]}
        )

    assert batch_response.status_code == 422
    assert batch_response.json()["error"]["code"] == "EMBEDDING_BATCH_TOO_LARGE"
    assert text_response.status_code == 422
    assert text_response.json()["error"]["code"] == "EMBEDDING_TEXT_TOO_LONG"
    assert service.calls == []


def test_embeddings_endpoint_enforces_total_character_limit() -> None:
    service = StubEmbeddingService()
    settings = ModelServiceSettings(
        ollama_batch_size=2,
        max_request_texts=2,
        max_text_chars=3,
        max_total_text_chars=4,
    )
    with TestClient(create_app(service=service, settings=settings)) as client:
        response = client.post(
            "/v1/embeddings", json={"model": "bge-m3", "texts": ["甲乙丙", "丁戊"]}
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMBEDDING_REQUEST_TOO_LARGE"
    assert service.calls == []


def test_embeddings_endpoint_sanitizes_provider_failure() -> None:
    service = StubEmbeddingService(
        error=EmbeddingServiceError(
            code="OLLAMA_UNAVAILABLE",
            message="Ollama embedding service is unavailable",
            status_code=503,
        )
    )
    with TestClient(create_app(service=service)) as client:
        response = client.post("/v1/embeddings", json={"model": "bge-m3", "texts": ["问题"]})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "OLLAMA_UNAVAILABLE",
            "message": "Ollama embedding service is unavailable",
        }
    }
    assert "http" not in response.text.lower()


def test_embeddings_endpoint_cancels_provider_when_total_timeout_expires() -> None:
    service = SlowEmbeddingService()
    settings = ModelServiceSettings(ollama_timeout_seconds=0.01)

    with TestClient(create_app(service=service, settings=settings)) as client:
        response = client.post("/v1/embeddings", json={"model": "bge-m3", "texts": ["问题"]})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OLLAMA_TIMEOUT"
    assert service.cancelled is True


def test_health_endpoints_distinguish_liveness_and_readiness() -> None:
    service = StubEmbeddingService(ready=False)
    with TestClient(create_app(service=service, rerank_service=StubRerankService())) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        compatibility = client.get("/health")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "dependencies": {"embedding": False, "rerank": True},
    }
    assert compatibility.status_code == 503


def test_health_ready_returns_dependency_status() -> None:
    service = StubEmbeddingService(ready=True)
    with TestClient(
        create_app(service=service, rerank_service=StubRerankService(ready=False))
    ) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "dependencies": {"embedding": True, "rerank": False},
    }


def test_rerank_endpoint_matches_backend_provider_contract() -> None:
    rerank = StubRerankService()
    with TestClient(create_app(service=StubEmbeddingService(), rerank_service=rerank)) as client:
        response = client.post(
            "/v1/rerank",
            json={
                "model": "BAAI/bge-reranker-v2-m3",
                "query": "如何部署？",
                "documents": ["先迁移数据库", "重启服务"],
                "top_k": 2,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "model": "BAAI/bge-reranker-v2-m3",
        "model_version": "revision-1",
        "results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.2}],
    }
    assert rerank.calls == [
        (
            "BAAI/bge-reranker-v2-m3",
            "如何部署？",
            ("先迁移数据库", "重启服务"),
            2,
        )
    ]


def test_rerank_endpoint_enforces_document_limits_and_sanitizes_failure() -> None:
    settings = ModelServiceSettings(
        rerank_max_documents=1,
        rerank_max_document_chars=3,
        rerank_max_total_document_chars=3,
    )
    rerank = StubRerankService(
        error=RerankServiceError(
            code="RERANK_UNAVAILABLE",
            message="Rerank service is unavailable",
            status_code=503,
        )
    )
    with TestClient(
        create_app(service=StubEmbeddingService(), rerank_service=rerank, settings=settings)
    ) as client:
        too_many = client.post(
            "/v1/rerank",
            json={"model": "reranker", "query": "问题", "documents": ["甲", "乙"], "top_k": 1},
        )
        failed = client.post(
            "/v1/rerank",
            json={"model": "reranker", "query": "问题", "documents": ["文档"], "top_k": 1},
        )

    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "RERANK_BATCH_TOO_LARGE"
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "RERANK_UNAVAILABLE"
