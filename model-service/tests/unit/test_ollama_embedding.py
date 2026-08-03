from __future__ import annotations

import asyncio
import json
import logging
import math

import httpx
import pytest

from knowagent_model.embedding import EmbeddingServiceError
from knowagent_model.ollama import OllamaEmbeddingConfig, OllamaEmbeddingService


def ollama_config(
    *,
    dimension: int,
    request_batch_size: int = 1,
    model: str = "bge-m3",
) -> OllamaEmbeddingConfig:
    return OllamaEmbeddingConfig(
        base_url="http://ollama:11434",
        model=model,
        model_version="ollama-bge-m3-daec91ff",
        expected_digest="daec91ff",
        dimension=dimension,
        request_batch_size=request_batch_size,
        max_concurrency=1,
        keep_alive="24h",
        health_timeout_seconds=5.0,
    )


def model_tags_response(
    *,
    name: str = "bge-m3:latest",
    digest: str = "daec91ff0123456789",
) -> httpx.Response:
    return httpx.Response(200, json={"models": [{"name": name, "digest": digest}]})


def test_embed_translates_batch_request_and_normalizes_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return model_tags_response()
        assert request.url == "http://ollama:11434/api/embed"
        assert json.loads(request.content) == {
            "model": "bge-m3",
            "input": ["问题一", "问题二"],
            "keep_alive": "24h",
        }
        return httpx.Response(
            200,
            json={
                "model": "bge-m3:latest",
                "embeddings": [[3.0, 4.0, 0.0], [0.0, 0.0, 2.0]],
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=3, request_batch_size=2),
            )
            result = await service.embed(model="bge-m3", texts=("问题一", "问题二"))

        assert result.model == "bge-m3"
        assert result.model_version == "ollama-bge-m3-daec91ff"
        assert result.dimension == 3
        assert result.normalized is True
        assert result.vectors[0] == pytest.approx((0.6, 0.8, 0.0))
        assert math.sqrt(sum(value * value for value in result.vectors[1])) == pytest.approx(1.0)

    asyncio.run(scenario())


def test_embed_falls_back_to_legacy_single_text_endpoint() -> None:
    requests: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            requests.append((request.url.path, None))
            return model_tags_response()
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if request.url.path == "/api/embed":
            return httpx.Response(404)
        prompt = payload["prompt"]
        vector = [1.0, 0.0] if prompt == "甲" else [0.0, 1.0]
        return httpx.Response(200, json={"embedding": vector})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=2, request_batch_size=2),
            )
            result = await service.embed(model="bge-m3", texts=("甲", "乙"))

        assert result.vectors == ((1.0, 0.0), (0.0, 1.0))

    asyncio.run(scenario())
    assert [path for path, _ in requests] == [
        "/api/tags",
        "/api/embed",
        "/api/embeddings",
        "/api/embeddings",
    ]


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        ({"model": "bge-m3", "embeddings": [[1.0, 2.0]]}, "EMBEDDING_DIMENSION_INVALID"),
        ({"model": "bge-m3", "embeddings": [[0.0, 0.0, 0.0]]}, "EMBEDDING_VECTOR_INVALID"),
        ({"model": "other", "embeddings": [[1.0, 0.0, 0.0]]}, "EMBEDDING_MODEL_MISMATCH"),
    ],
)
def test_embed_rejects_invalid_ollama_contract(payload: dict[str, object], error_code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return model_tags_response()
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=3),
            )
            with pytest.raises(EmbeddingServiceError) as captured:
                await service.embed(model="bge-m3", texts=("问题",))

        assert captured.value.code == error_code

    asyncio.run(scenario())


def test_ready_requires_configured_model_in_ollama_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://ollama:11434/api/tags"
        assert request.extensions["timeout"]["read"] == 5.0
        return model_tags_response()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=1024),
            )
            assert await service.ready() is True

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"models": "invalid"}),
        httpx.Response(
            200,
            json={"models": [{"name": "other:latest", "digest": "daec91ff"}, "invalid"]},
        ),
    ],
)
def test_ready_returns_false_for_unavailable_or_missing_model(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return response

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=1024),
            )
            assert await service.ready() is False

    asyncio.run(scenario())


def test_embed_maps_ollama_http_error_without_leaking_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return model_tags_response()
        raise httpx.ConnectError("secret internal address", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=3),
            )
            with pytest.raises(EmbeddingServiceError) as captured:
                await service.embed(model="bge-m3", texts=("问题",))

        assert captured.value.code == "OLLAMA_UNAVAILABLE"
        assert "secret" not in str(captured.value)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("configured_model", "actual_name", "actual_digest"),
    [
        ("bge-m3:v1", "bge-m3:v2", "daec91ff0123456789"),
        ("bge-m3", "bge-m3:latest", "different-digest"),
        ("bge-m3", "bge-m3:latest", ""),
    ],
)
def test_model_identity_mismatch_blocks_readiness_and_embedding(
    configured_model: str,
    actual_name: str,
    actual_digest: str,
) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return model_tags_response(name=actual_name, digest=actual_digest)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=3, model=configured_model),
            )
            assert await service.ready() is False
            with pytest.raises(EmbeddingServiceError) as captured:
                await service.embed(model=configured_model, texts=("问题",))

        assert captured.value.code == "OLLAMA_MODEL_IDENTITY_INVALID"

    asyncio.run(scenario())
    assert requested_paths == ["/api/tags", "/api/tags"]


@pytest.mark.parametrize(
    "raw_vector",
    [
        "111",
        {"0": 1.0, "1": 0.0, "2": 0.0},
        [True, 0.0, 0.0],
        ["1", 0.0, 0.0],
        [10**400, 0.0, 0.0],
    ],
)
def test_embed_rejects_non_numeric_json_array_vectors(raw_vector: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return model_tags_response()
        return httpx.Response(
            200,
            json={"model": "bge-m3:latest", "embeddings": [raw_vector]},
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(client=client, config=ollama_config(dimension=3))
            with pytest.raises(EmbeddingServiceError) as captured:
                await service.embed(model="bge-m3", texts=("问题",))

        assert captured.value.code == "EMBEDDING_VECTOR_INVALID"

    asyncio.run(scenario())


def test_embed_logs_sanitized_outcome_and_latency(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return model_tags_response()
        raise httpx.ConnectError("secret internal address", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(client=client, config=ollama_config(dimension=3))
            with pytest.raises(EmbeddingServiceError):
                await service.embed(model="bge-m3", texts=("sensitive question",))

    caplog.set_level(logging.INFO, logger="knowagent_model.ollama")
    asyncio.run(scenario())

    failure = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("ollama embedding failed")
    )
    provider_failure = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("ollama provider request failed")
    )
    assert failure.__dict__.get("error_code") == "OLLAMA_UNAVAILABLE"
    assert failure.__dict__.get("duration_ms", -1) >= 0
    assert failure.__dict__.get("text_count") == 1
    assert provider_failure.__dict__.get("error_type") == "ConnectError"
    assert "error_code=OLLAMA_UNAVAILABLE" in caplog.text
    assert "error_type=ConnectError" in caplog.text
    assert "secret" not in caplog.text
    assert "sensitive question" not in caplog.text


def test_embed_rejects_unconfigured_model_before_ollama_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OllamaEmbeddingService(
                client=client,
                config=ollama_config(dimension=3),
            )
            with pytest.raises(EmbeddingServiceError) as captured:
                await service.embed(model="other", texts=("问题",))

        assert captured.value.code == "EMBEDDING_MODEL_UNSUPPORTED"
        assert captured.value.status_code == 422

    asyncio.run(scenario())
