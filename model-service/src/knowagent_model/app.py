from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowagent_model.embedding import EmbeddingService, EmbeddingServiceError
from knowagent_model.ollama import OllamaEmbeddingConfig, OllamaEmbeddingService
from knowagent_model.settings import ModelServiceSettings


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Annotated[str, Field(min_length=1)]
    texts: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be blank")
        return value.strip()

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("texts must not contain blank values")
        return [value.strip() for value in values]


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    model_version: str
    dimension: int
    normalized: bool
    vectors: list[list[float]]


def create_app(
    *,
    service: EmbeddingService | None = None,
    settings: ModelServiceSettings | None = None,
) -> FastAPI:
    configured_settings = settings or ModelServiceSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            application.state.embedding_service = service
            yield
            return
        async with httpx.AsyncClient(timeout=configured_settings.ollama_timeout_seconds) as client:
            application.state.embedding_service = OllamaEmbeddingService(
                client=client,
                config=OllamaEmbeddingConfig(
                    base_url=configured_settings.ollama_base_url,
                    model=configured_settings.embedding_model,
                    model_version=configured_settings.embedding_model_version,
                    expected_digest=configured_settings.ollama_model_digest,
                    dimension=configured_settings.embedding_dimension,
                    request_batch_size=configured_settings.ollama_batch_size,
                    max_concurrency=configured_settings.ollama_max_concurrency,
                    keep_alive=configured_settings.ollama_keep_alive,
                    health_timeout_seconds=configured_settings.ollama_health_timeout_seconds,
                ),
            )
            yield

    application = FastAPI(title="KnowAgent Model Service", version="0.1.0", lifespan=lifespan)

    @application.exception_handler(EmbeddingServiceError)
    async def handle_embedding_error(
        request: Request, error: EmbeddingServiceError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    def get_service() -> EmbeddingService:
        return cast(EmbeddingService, application.state.embedding_service)

    @application.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "alive"}

    async def readiness_response() -> JSONResponse:
        is_ready = await get_service().ready()
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "dependencies": {"ollama": is_ready},
            },
        )

    application.add_api_route("/health/ready", readiness_response, methods=["GET"])
    application.add_api_route(
        "/health", readiness_response, methods=["GET"], include_in_schema=False
    )

    @application.post("/v1/embeddings", response_model=EmbeddingResponse)
    async def create_embeddings(payload: EmbeddingRequest) -> EmbeddingResponse:
        if len(payload.texts) > configured_settings.max_request_texts:
            raise EmbeddingServiceError(
                code="EMBEDDING_BATCH_TOO_LARGE",
                message="Embedding request contains too many texts",
                status_code=422,
            )
        if any(len(text) > configured_settings.max_text_chars for text in payload.texts):
            raise EmbeddingServiceError(
                code="EMBEDDING_TEXT_TOO_LONG",
                message="Embedding text exceeds the configured character limit",
                status_code=422,
            )
        if sum(len(text) for text in payload.texts) > configured_settings.max_total_text_chars:
            raise EmbeddingServiceError(
                code="EMBEDDING_REQUEST_TOO_LARGE",
                message="Embedding request exceeds the total character limit",
                status_code=422,
            )
        result = await get_service().embed(model=payload.model, texts=tuple(payload.texts))
        return EmbeddingResponse(
            model=result.model,
            model_version=result.model_version,
            dimension=result.dimension,
            normalized=result.normalized,
            vectors=[list(vector) for vector in result.vectors],
        )

    return application


app = create_app()
