from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.domain.models import FusedSearchHit, RetrievalResult, SearchHit
from knowagent.retrieval.ports import (
    EmbeddingProvider,
    LexicalSearchProvider,
    RetrievalMetrics,
    VectorSearchProvider,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _FusionEntry:
    hit: SearchHit
    fused_score: float = 0.0
    channels: tuple[str, ...] = ()


class BasicRetrievalService:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    # Constructor arguments are explicit ports and independently configured retrieval limits.
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        lexical: LexicalSearchProvider,
        vectors: VectorSearchProvider,
        keyword_top_k: int,
        vector_top_k: int,
        result_top_k: int,
        rrf_k: int,
        metrics: RetrievalMetrics,
    ) -> None:
        limits = (keyword_top_k, vector_top_k, result_top_k, rrf_k)
        if any(value <= 0 for value in limits):
            raise ValueError("retrieval limits must be positive")
        if result_top_k > keyword_top_k + vector_top_k:
            raise ValueError("result_top_k exceeds the available candidate budget")
        self._embeddings = embeddings
        self._lexical = lexical
        self._vectors = vectors
        self._keyword_top_k = keyword_top_k
        self._vector_top_k = vector_top_k
        self._result_top_k = result_top_k
        self._rrf_k = rrf_k
        self._metrics = metrics

    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValidationError("QUESTION_EMPTY", "问题不能为空")

        keyword_hits = self._lexical.search(
            system_id=system_id,
            query=normalized_query,
            limit=self._keyword_top_k,
        )
        try:
            batch = await self._embeddings.embed(texts=(normalized_query,))
        except ProviderUnavailableError:
            return self._degraded_result(
                system_id=system_id,
                query=normalized_query,
                keyword_hits=keyword_hits,
                reason="embedding_unavailable",
            )
        try:
            vector_hits = self._vectors.search_vectors(
                system_id=system_id,
                vector=batch.vectors[0],
                model=batch.model,
                model_version=batch.model_version,
                limit=self._vector_top_k,
            )
        except ProviderUnavailableError:
            return self._degraded_result(
                system_id=system_id,
                query=normalized_query,
                keyword_hits=keyword_hits,
                reason="vector_search_unavailable",
            )

        fused = self._fuse(("keyword", keyword_hits), ("vector", vector_hits))
        return RetrievalResult(
            query=normalized_query,
            hits=fused[: self._result_top_k],
            degraded_reasons=(),
        )

    def _degraded_result(
        self,
        *,
        system_id: UUID,
        query: str,
        keyword_hits: tuple[SearchHit, ...],
        reason: str,
    ) -> RetrievalResult:
        LOGGER.warning(
            "vector retrieval degraded",
            extra={"system_id": str(system_id), "channel": "vector", "reason": reason},
        )
        self._metrics.record_degradation(
            system_id=system_id,
            channel="vector",
            reason=reason,
        )
        fused = self._fuse(("keyword", keyword_hits))
        return RetrievalResult(
            query=query,
            hits=fused[: self._result_top_k],
            degraded_reasons=("VECTOR_UNAVAILABLE",),
        )

    def _fuse(
        self,
        *channels: tuple[str, tuple[SearchHit, ...]],
    ) -> tuple[FusedSearchHit, ...]:
        entries: dict[UUID, _FusionEntry] = {}
        channel_order: dict[UUID, list[str]] = defaultdict(list)
        for channel, hits in channels:
            for rank, hit in enumerate(hits, start=1):
                entry = entries.setdefault(hit.chunk_id, _FusionEntry(hit=hit))
                entry.fused_score += 1.0 / (self._rrf_k + rank)
                channel_order[hit.chunk_id].append(channel)
        ordered = sorted(
            entries.values(),
            key=lambda entry: (-entry.fused_score, str(entry.hit.chunk_id)),
        )
        return tuple(
            FusedSearchHit.from_search_hit(
                entry.hit,
                fused_score=entry.fused_score,
                channels=tuple(channel_order[entry.hit.chunk_id]),
            )
            for entry in ordered
        )
