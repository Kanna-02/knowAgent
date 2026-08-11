from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.domain.models import RerankBatch, RerankScore


class _RerankResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    score: float = Field(allow_inf_nan=False)


class _RerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    results: list[_RerankResultResponse] = Field(min_length=1)


class HttpRerankProvider:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: int,
        failure_cooldown_seconds: int = 60,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise ValueError("rerank provider configuration is incomplete")
        if timeout_seconds <= 0:
            raise ValueError("rerank timeout must be positive")
        if failure_cooldown_seconds <= 0:
            raise ValueError("rerank failure cooldown must be positive")
        self._url = f"{base_url.rstrip('/')}/rerank"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._failure_cooldown_seconds = failure_cooldown_seconds
        self._failure_until = 0.0
        self._client = client

    async def rerank(
        self,
        *,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch:
        normalized_query = query.strip()
        if not normalized_query or not documents or any(not item.strip() for item in documents):
            raise ValidationError("RERANK_INPUT_INVALID", "重排问题和候选文本不能为空")
        if top_k <= 0 or top_k > len(documents):
            raise ValidationError("RERANK_TOP_K_INVALID", "重排结果数量超出候选范围")
        if time.monotonic() < self._failure_until:
            raise ProviderUnavailableError("rerank")

        client = self._client or httpx.AsyncClient()
        owns_client = self._client is None
        try:
            response = await client.post(
                self._url,
                json={
                    "model": self._model,
                    "query": normalized_query,
                    "documents": list(documents),
                    "top_k": top_k,
                },
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                raise ProviderUnavailableError("rerank")
            payload = _RerankResponse.model_validate(response.json())
            self._validate_response(payload=payload, document_count=len(documents), top_k=top_k)
            self._failure_until = 0.0
            return RerankBatch(
                model=payload.model,
                model_version=payload.model_version,
                results=tuple(
                    RerankScore(index=result.index, score=result.score)
                    for result in payload.results
                ),
            )
        except (
            ProviderUnavailableError,
            httpx.HTTPError,
            PydanticValidationError,
            ValueError,
            TypeError,
        ) as error:
            self._failure_until = time.monotonic() + self._failure_cooldown_seconds
            raise ProviderUnavailableError("rerank") from error
        finally:
            if owns_client:
                await client.aclose()

    def _validate_response(
        self,
        *,
        payload: _RerankResponse,
        document_count: int,
        top_k: int,
    ) -> None:
        indexes = [result.index for result in payload.results]
        scores = [result.score for result in payload.results]
        if payload.model != self._model or len(payload.results) != top_k:
            raise ValueError("rerank response metadata does not match request")
        if len(set(indexes)) != len(indexes) or any(index >= document_count for index in indexes):
            raise ValueError("rerank response indexes are invalid")
        if scores != sorted(scores, reverse=True):
            raise ValueError("rerank response scores are not ordered")
