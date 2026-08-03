from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.domain.models import EmbeddingBatch


class _EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    normalized: bool
    vectors: list[list[float]] = Field(min_length=1)


class HttpEmbeddingProvider:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise ValueError("embedding provider configuration is incomplete")
        if timeout_seconds <= 0:
            raise ValueError("embedding timeout must be positive")
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch:
        if not texts or any(not text.strip() for text in texts):
            raise ValidationError("EMBEDDING_TEXT_INVALID", "向量文本不能为空")
        client = self._client or httpx.AsyncClient()
        owns_client = self._client is None
        try:
            response = await client.post(
                self._url,
                json={"model": self._model, "texts": list(texts)},
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                raise ProviderUnavailableError("embedding")
            payload = _EmbeddingResponse.model_validate(response.json())
            if payload.model != self._model or len(payload.vectors) != len(texts):
                raise ProviderUnavailableError("embedding")
            return EmbeddingBatch(
                model=payload.model,
                model_version=payload.model_version,
                dimension=payload.dimension,
                normalized=payload.normalized,
                vectors=tuple(tuple(vector) for vector in payload.vectors),
            )
        except (httpx.HTTPError, PydanticValidationError, ValueError, TypeError) as error:
            raise ProviderUnavailableError("embedding") from error
        finally:
            if owns_client:
                await client.aclose()
