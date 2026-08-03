from __future__ import annotations

from fastapi.testclient import TestClient

from knowagent_model.app import create_app
from knowagent_model.embedding import EmbeddingBatch, EmbeddingServiceError
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
    settings = ModelServiceSettings(max_request_texts=1, max_text_chars=3, max_total_text_chars=3)
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
    settings = ModelServiceSettings(max_request_texts=2, max_text_chars=3, max_total_text_chars=4)
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


def test_health_endpoints_distinguish_liveness_and_readiness() -> None:
    service = StubEmbeddingService(ready=False)
    with TestClient(create_app(service=service)) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        compatibility = client.get("/health")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "dependencies": {"ollama": False}}
    assert compatibility.status_code == 503


def test_health_ready_returns_dependency_status() -> None:
    service = StubEmbeddingService(ready=True)
    with TestClient(create_app(service=service)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {"ollama": True}}
