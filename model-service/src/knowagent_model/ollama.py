from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

import httpx

from knowagent_model.embedding import EmbeddingBatch, EmbeddingServiceError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OllamaEmbeddingConfig:
    base_url: str
    model: str
    model_version: str
    expected_digest: str
    dimension: int
    request_batch_size: int
    max_concurrency: int
    keep_alive: str
    health_timeout_seconds: float


class OllamaEmbeddingService:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        config: OllamaEmbeddingConfig,
    ) -> None:
        self._client = client
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)

    async def embed(self, *, model: str, texts: tuple[str, ...]) -> EmbeddingBatch:
        if model != self._config.model:
            raise EmbeddingServiceError(
                code="EMBEDDING_MODEL_UNSUPPORTED",
                message="Requested embedding model is not available",
                status_code=422,
            )
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingServiceError(
                code="EMBEDDING_TEXT_INVALID",
                message="Embedding texts must not be empty",
                status_code=422,
            )

        started = time.monotonic()
        try:
            async with self._semaphore:
                identity_valid, _ = await self._model_identity_status()
                if not identity_valid:
                    raise EmbeddingServiceError(
                        code="OLLAMA_MODEL_IDENTITY_INVALID",
                        message="Configured Ollama embedding model is not ready",
                        status_code=503,
                    )
                result = await self._embed_serialized(texts)
        except EmbeddingServiceError as error:
            duration_ms = self._duration_ms(started)
            LOGGER.warning(
                "ollama embedding failed operation=embedding outcome=error "
                "error_code=%s status_code=%s duration_ms=%s text_count=%s",
                error.code,
                error.status_code,
                duration_ms,
                len(texts),
                extra={
                    "operation": "embedding",
                    "outcome": "error",
                    "error_code": error.code,
                    "status_code": error.status_code,
                    "duration_ms": duration_ms,
                    "text_count": len(texts),
                },
            )
            raise
        duration_ms = self._duration_ms(started)
        LOGGER.info(
            "ollama embedding completed operation=embedding outcome=success "
            "duration_ms=%s text_count=%s vector_count=%s",
            duration_ms,
            len(texts),
            len(result.vectors),
            extra={
                "operation": "embedding",
                "outcome": "success",
                "duration_ms": duration_ms,
                "text_count": len(texts),
                "vector_count": len(result.vectors),
            },
        )
        return result

    async def _embed_serialized(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        vectors: list[tuple[float, ...]] = []
        use_legacy_endpoint = False
        for offset in range(0, len(texts), self._config.request_batch_size):
            batch = texts[offset : offset + self._config.request_batch_size]
            if use_legacy_endpoint:
                raw_vectors = await self._embed_legacy(batch)
            else:
                raw_vectors, use_legacy_endpoint = await self._embed_batch(batch)
            vectors.extend(self._normalize_vector(vector) for vector in raw_vectors)

        if len(vectors) != len(texts):
            raise self._invalid_contract("EMBEDDING_COUNT_INVALID")
        return EmbeddingBatch(
            model=self._config.model,
            model_version=self._config.model_version,
            dimension=self._config.dimension,
            normalized=True,
            vectors=tuple(vectors),
        )

    async def ready(self) -> bool:
        identity_valid, _ = await self._model_identity_status()
        return identity_valid

    async def _model_identity_status(self) -> tuple[bool, str]:
        started = time.monotonic()
        try:
            response = await self._client.get(
                f"{self._config.base_url.rstrip('/')}/api/tags",
                timeout=self._config.health_timeout_seconds,
            )
            if response.status_code >= 400:
                self._log_identity_result(
                    started=started,
                    outcome="error",
                    reason="http_error",
                    status_code=response.status_code,
                )
                return False, "http_error"
            payload = response.json()
            models = payload.get("models")
            if not isinstance(models, list):
                self._log_identity_result(
                    started=started,
                    outcome="error",
                    reason="invalid_response",
                )
                return False, "invalid_response"
            identity_valid = any(self._tag_matches(item) for item in models)
            reason = "verified" if identity_valid else "model_identity_mismatch"
            self._log_identity_result(
                started=started,
                outcome="success" if identity_valid else "error",
                reason=reason,
            )
            return identity_valid, reason
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as error:
            self._log_identity_result(
                started=started,
                outcome="error",
                reason="request_error",
                error_type=type(error).__name__,
            )
            return False, "request_error"

    async def _embed_batch(self, texts: tuple[str, ...]) -> tuple[list[object], bool]:
        try:
            response = await self._client.post(
                f"{self._config.base_url.rstrip('/')}/api/embed",
                json={
                    "model": self._config.model,
                    "input": list(texts),
                    "keep_alive": self._config.keep_alive,
                },
            )
        except httpx.HTTPError as error:
            self._log_provider_request_error(operation="embed_batch", error=error)
            raise self._unavailable() from error
        if response.status_code == 404:
            return await self._embed_legacy(texts), True
        if response.status_code >= 400:
            self._log_provider_http_error(
                operation="embed_batch", status_code=response.status_code
            )
            raise self._unavailable()

        try:
            payload = response.json()
            if not self._model_names_match(payload.get("model"), self._config.model):
                raise self._invalid_contract("EMBEDDING_MODEL_MISMATCH")
            vectors = payload.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise self._invalid_contract("EMBEDDING_COUNT_INVALID")
            return vectors, False
        except (ValueError, TypeError, AttributeError) as error:
            raise self._invalid_contract("EMBEDDING_RESPONSE_INVALID") from error

    async def _embed_legacy(self, texts: tuple[str, ...]) -> list[object]:
        vectors: list[object] = []
        for text in texts:
            try:
                response = await self._client.post(
                    f"{self._config.base_url.rstrip('/')}/api/embeddings",
                    json={
                        "model": self._config.model,
                        "prompt": text,
                        "keep_alive": self._config.keep_alive,
                    },
                )
            except httpx.HTTPError as error:
                self._log_provider_request_error(operation="embed_legacy", error=error)
                raise self._unavailable() from error
            if response.status_code >= 400:
                self._log_provider_http_error(
                    operation="embed_legacy", status_code=response.status_code
                )
                raise self._unavailable()
            try:
                payload = response.json()
                vector = payload.get("embedding")
                if not isinstance(vector, list):
                    raise self._invalid_contract("EMBEDDING_RESPONSE_INVALID")
                vectors.append(vector)
            except (ValueError, TypeError, AttributeError) as error:
                raise self._invalid_contract("EMBEDDING_RESPONSE_INVALID") from error
        return vectors

    def _normalize_vector(self, raw_vector: object) -> tuple[float, ...]:
        if not isinstance(raw_vector, list):
            raise self._invalid_contract("EMBEDDING_VECTOR_INVALID")
        if len(raw_vector) != self._config.dimension:
            raise self._invalid_contract("EMBEDDING_DIMENSION_INVALID")
        vector_values: list[float] = []
        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise self._invalid_contract("EMBEDDING_VECTOR_INVALID")
            try:
                vector_values.append(float(value))
            except OverflowError as error:
                raise self._invalid_contract("EMBEDDING_VECTOR_INVALID") from error
        vector = tuple(vector_values)
        if any(not math.isfinite(value) for value in vector):
            raise self._invalid_contract("EMBEDDING_VECTOR_INVALID")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(norm) or norm == 0:
            raise self._invalid_contract("EMBEDDING_VECTOR_INVALID")
        return tuple(value / norm for value in vector)

    def _tag_matches(self, item: object) -> bool:
        if not isinstance(item, dict):
            return False
        name = item.get("name")
        digest = item.get("digest")
        return (
            self._model_names_match(name, self._config.model)
            and isinstance(digest, str)
            and self._normalize_digest(digest).startswith(
                self._normalize_digest(self._config.expected_digest)
            )
        )

    @staticmethod
    def _model_names_match(actual: object, expected: str) -> bool:
        if not isinstance(actual, str):
            return False
        if ":" in expected:
            return actual == expected
        return actual in {expected, f"{expected}:latest"}

    @staticmethod
    def _normalize_digest(value: str) -> str:
        normalized = value.strip().lower()
        return normalized.removeprefix("sha256:")

    @staticmethod
    def _duration_ms(started: float) -> float:
        return round((time.monotonic() - started) * 1000, 3)

    def _log_identity_result(
        self,
        *,
        started: float,
        outcome: str,
        reason: str,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        log = LOGGER.info if outcome == "success" else LOGGER.warning
        duration_ms = self._duration_ms(started)
        log(
            "ollama model identity checked operation=model_identity outcome=%s "
            "reason=%s status_code=%s error_type=%s duration_ms=%s",
            outcome,
            reason,
            status_code,
            error_type,
            duration_ms,
            extra={
                "operation": "model_identity",
                "outcome": outcome,
                "reason": reason,
                "status_code": status_code,
                "error_type": error_type,
                "duration_ms": duration_ms,
            },
        )

    @staticmethod
    def _log_provider_request_error(*, operation: str, error: httpx.HTTPError) -> None:
        LOGGER.warning(
            "ollama provider request failed operation=%s outcome=error error_type=%s",
            operation,
            type(error).__name__,
            extra={
                "operation": operation,
                "outcome": "error",
                "error_type": type(error).__name__,
            },
        )

    @staticmethod
    def _log_provider_http_error(*, operation: str, status_code: int) -> None:
        LOGGER.warning(
            "ollama provider returned an error operation=%s outcome=error status_code=%s",
            operation,
            status_code,
            extra={
                "operation": operation,
                "outcome": "error",
                "status_code": status_code,
            },
        )

    @staticmethod
    def _unavailable() -> EmbeddingServiceError:
        return EmbeddingServiceError(
            code="OLLAMA_UNAVAILABLE",
            message="Ollama embedding service is unavailable",
            status_code=503,
        )

    @staticmethod
    def _invalid_contract(code: str) -> EmbeddingServiceError:
        return EmbeddingServiceError(
            code=code,
            message="Ollama returned an invalid embedding response",
            status_code=502,
        )
