from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, NoReturn, cast

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowagent_model.embedding import EmbeddingBatch, EmbeddingService, EmbeddingServiceError
from knowagent_model.flag_embedding import (
    FlagEmbeddingRerankConfig,
    FlagEmbeddingRerankService,
)
from knowagent_model.ollama import OllamaEmbeddingConfig, OllamaEmbeddingService
from knowagent_model.rerank import RerankService, RerankServiceError
from knowagent_model.settings import ModelServiceSettings


async def _wait_for_disconnect(request: Request) -> None:
    while not await request.is_disconnected():
        await asyncio.sleep(0.1)


async def _embed_until_disconnect(
    *,
    request: Request,
    service: EmbeddingService,
    model: str,
    texts: tuple[str, ...],
) -> EmbeddingBatch:
    embedding_task = asyncio.create_task(service.embed(model=model, texts=texts))
    disconnect_task = asyncio.create_task(_wait_for_disconnect(request))
    try:
        done, _ = await asyncio.wait(
            {embedding_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if embedding_task in done:
            return await embedding_task
        embedding_task.cancel()
        await asyncio.gather(embedding_task, return_exceptions=True)
        raise EmbeddingServiceError(
            code="CLIENT_DISCONNECTED",
            message="Embedding request was cancelled",
            status_code=499,
        )
    finally:
        disconnect_task.cancel()
        if not embedding_task.done():
            embedding_task.cancel()


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


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Annotated[str, Field(min_length=1)]
    query: Annotated[str, Field(min_length=1)]
    documents: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    top_k: Annotated[int, Field(gt=0)]

    @field_validator("model", "query")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("documents must not contain blank values")
        return [value.strip() for value in values]


class RerankResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    score: float


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    model_version: str
    results: list[RerankResultResponse]


class _UnavailableRerankService:  # pylint: disable=too-few-public-methods
    async def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> "NoReturn":
        del model, query, documents, top_k
        raise RerankServiceError(
            code="RERANK_UNAVAILABLE",
            message="Rerank service is unavailable",
            status_code=503,
        )

    async def ready(self) -> bool:
        return False


def create_app(
    *,
    service: EmbeddingService | None = None,
    rerank_service: RerankService | None = None,
    settings: ModelServiceSettings | None = None,
) -> FastAPI:
    configured_settings = settings or ModelServiceSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            application.state.embedding_service = service
            application.state.rerank_service = rerank_service or _UnavailableRerankService()
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
            application.state.rerank_service = rerank_service or FlagEmbeddingRerankService(
                config=FlagEmbeddingRerankConfig(
                    model=configured_settings.rerank_model,
                    model_version=configured_settings.rerank_model_version,
                    batch_size=configured_settings.rerank_batch_size,
                    max_length=configured_settings.rerank_max_length,
                    max_concurrency=configured_settings.rerank_max_concurrency,
                    use_fp16=configured_settings.rerank_use_fp16,
                    device=configured_settings.rerank_device,
                    model_path=configured_settings.rerank_model_path,
                )
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

    @application.exception_handler(RerankServiceError)
    async def handle_rerank_error(request: Request, error: RerankServiceError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    def get_service() -> EmbeddingService:
        return cast(EmbeddingService, application.state.embedding_service)

    def get_rerank_service() -> RerankService:
        return cast(RerankService, application.state.rerank_service)

    @application.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "alive"}

    async def readiness_response() -> JSONResponse:
        embedding_ready = await get_service().ready()
        rerank_ready = await get_rerank_service().ready()
        status = "not_ready" if not embedding_ready else "ready" if rerank_ready else "degraded"
        return JSONResponse(
            status_code=200 if embedding_ready else 503,
            content={
                "status": status,
                "dependencies": {"embedding": embedding_ready, "rerank": rerank_ready},
            },
        )

    application.add_api_route("/health/ready", readiness_response, methods=["GET"])
    application.add_api_route(
        "/health", readiness_response, methods=["GET"], include_in_schema=False
    )

    @application.post("/v1/embeddings", response_model=EmbeddingResponse)
    async def create_embeddings(request: Request, payload: EmbeddingRequest) -> EmbeddingResponse:
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
        try:
            async with asyncio.timeout(configured_settings.ollama_timeout_seconds):
                result = await _embed_until_disconnect(
                    request=request,
                    service=get_service(),
                    model=payload.model,
                    texts=tuple(payload.texts),
                )
        except TimeoutError as error:
            raise EmbeddingServiceError(
                code="OLLAMA_TIMEOUT",
                message="Ollama embedding request timed out",
                status_code=503,
            ) from error
        return EmbeddingResponse(
            model=result.model,
            model_version=result.model_version,
            dimension=result.dimension,
            normalized=result.normalized,
            vectors=[list(vector) for vector in result.vectors],
        )

    @application.post("/v1/rerank", response_model=RerankResponse)
    async def rerank_documents(payload: RerankRequest) -> RerankResponse:
        if len(payload.documents) > configured_settings.rerank_max_documents:
            raise RerankServiceError(
                code="RERANK_BATCH_TOO_LARGE",
                message="Rerank request contains too many documents",
                status_code=422,
            )
        if len(payload.query) > configured_settings.rerank_max_query_chars:
            raise RerankServiceError(
                code="RERANK_QUERY_TOO_LONG",
                message="Rerank query exceeds the configured character limit",
                status_code=422,
            )
        if any(
            len(document) > configured_settings.rerank_max_document_chars
            for document in payload.documents
        ):
            raise RerankServiceError(
                code="RERANK_DOCUMENT_TOO_LONG",
                message="Rerank document exceeds the configured character limit",
                status_code=422,
            )
        if (
            sum(len(document) for document in payload.documents)
            > configured_settings.rerank_max_total_document_chars
        ):
            raise RerankServiceError(
                code="RERANK_REQUEST_TOO_LARGE",
                message="Rerank request exceeds the total character limit",
                status_code=422,
            )
        if payload.top_k > len(payload.documents):
            raise RerankServiceError(
                code="RERANK_TOP_K_INVALID",
                message="Rerank top_k exceeds the candidate count",
                status_code=422,
            )
        result = await get_rerank_service().rerank(
            model=payload.model,
            query=payload.query,
            documents=tuple(payload.documents),
            top_k=payload.top_k,
        )
        return RerankResponse(
            model=result.model,
            model_version=result.model_version,
            results=[
                RerankResultResponse(index=item.index, score=item.score) for item in result.results
            ],
        )

    return application


app = create_app()
