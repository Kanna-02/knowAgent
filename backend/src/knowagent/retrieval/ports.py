from __future__ import annotations

from typing import Protocol
from uuid import UUID

from knowagent.retrieval.domain.models import EmbeddingBatch, RerankBatch, SearchHit

# Provider ports intentionally expose one operation per retrieval channel.
# pylint: disable=too-few-public-methods


class EmbeddingProvider(Protocol):
    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch: ...


class LexicalSearchProvider(Protocol):
    def search(self, *, system_id: UUID, query: str, limit: int) -> tuple[SearchHit, ...]: ...


class VectorSearchProvider(Protocol):
    def search_vectors(
        self,
        *,
        system_id: UUID,
        vector: tuple[float, ...],
        model: str,
        model_version: str,
        limit: int,
    ) -> tuple[SearchHit, ...]: ...


class RerankProvider(Protocol):
    async def rerank(
        self,
        *,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch: ...


class RetrievalMetrics(Protocol):
    def record_degradation(self, *, system_id: UUID, channel: str, reason: str) -> None: ...
