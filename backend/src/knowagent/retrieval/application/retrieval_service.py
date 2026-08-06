from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from uuid import UUID

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.domain.models import FusedSearchHit, RetrievalResult, SearchHit
from knowagent.retrieval.ports import (
    EmbeddingProvider,
    LexicalSearchProvider,
    RerankProvider,
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
    def __init__(  # pylint: disable=too-many-locals
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
        reranker: RerankProvider | None = None,
        rerank_candidate_top_k: int | None = None,
        rerank_top_k: int | None = None,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> None:
        limits = (keyword_top_k, vector_top_k, result_top_k, rrf_k)
        if any(value <= 0 for value in limits):
            raise ValueError("retrieval limits must be positive")
        if result_top_k > keyword_top_k + vector_top_k:
            raise ValueError("result_top_k exceeds the available candidate budget")
        weights = (keyword_weight, vector_weight)
        if any(not math.isfinite(value) or value <= 0 for value in weights):
            raise ValueError("retrieval channel weights must be positive and finite")
        if reranker is not None:
            if rerank_candidate_top_k is None or rerank_top_k is None:
                raise ValueError("rerank candidate and result limits are required")
            if not result_top_k <= rerank_top_k <= rerank_candidate_top_k:
                raise ValueError("rerank limits must cover the configured result limit")
            if rerank_candidate_top_k > keyword_top_k + vector_top_k:
                raise ValueError("rerank candidate limit exceeds the retrieval budget")
        self._embeddings = embeddings
        self._lexical = lexical
        self._vectors = vectors
        self._keyword_top_k = keyword_top_k
        self._vector_top_k = vector_top_k
        self._result_top_k = result_top_k
        self._rrf_k = rrf_k
        self._metrics = metrics
        self._reranker = reranker
        self._rerank_candidate_top_k = rerank_candidate_top_k
        self._rerank_top_k = rerank_top_k
        self._weights = {"keyword": keyword_weight, "vector": vector_weight}

    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValidationError("QUESTION_EMPTY", "问题不能为空")

        keyword_hits = self._lexical.search(
            system_id=system_id,
            query=normalized_query,
            limit=self._keyword_top_k,
        )
        vector_hits, vector_degradation = await self._retrieve_vectors(
            system_id=system_id,
            query=normalized_query,
        )
        degraded_reasons = [vector_degradation] if vector_degradation is not None else []
        fused = self._fuse(("keyword", keyword_hits), ("vector", vector_hits))
        ranked = await self._rerank(
            system_id=system_id,
            query=normalized_query,
            fused=fused,
            degraded_reasons=degraded_reasons,
        )
        return RetrievalResult(
            query=normalized_query,
            hits=ranked[: self._result_top_k],
            degraded_reasons=tuple(degraded_reasons),
        )

    async def _retrieve_vectors(
        self,
        *,
        system_id: UUID,
        query: str,
    ) -> tuple[tuple[SearchHit, ...], str | None]:
        try:
            batch = await self._embeddings.embed(texts=(query,))
        except ProviderUnavailableError:
            self._record_degradation(
                system_id=system_id,
                channel="vector",
                reason="embedding_unavailable",
            )
            return (), "VECTOR_UNAVAILABLE"
        try:
            return (
                self._vectors.search_vectors(
                    system_id=system_id,
                    vector=batch.vectors[0],
                    model=batch.model,
                    model_version=batch.model_version,
                    limit=self._vector_top_k,
                ),
                None,
            )
        except ProviderUnavailableError:
            self._record_degradation(
                system_id=system_id,
                channel="vector",
                reason="vector_search_unavailable",
            )
            return (), "VECTOR_UNAVAILABLE"

    async def _rerank(
        self,
        *,
        system_id: UUID,
        query: str,
        fused: tuple[FusedSearchHit, ...],
        degraded_reasons: list[str],
    ) -> tuple[FusedSearchHit, ...]:
        if self._reranker is None or not fused:
            return fused
        assert self._rerank_candidate_top_k is not None
        assert self._rerank_top_k is not None
        candidates = fused[: self._rerank_candidate_top_k]
        started = time.perf_counter()
        try:
            batch = await self._reranker.rerank(
                query=query,
                documents=tuple(hit.text for hit in candidates),
                top_k=min(self._rerank_top_k, len(candidates)),
            )
            if any(item.index >= len(candidates) for item in batch.results):
                raise ProviderUnavailableError("rerank")
        except ProviderUnavailableError:
            self._record_degradation(
                system_id=system_id,
                channel="rerank",
                reason="rerank_unavailable",
            )
            degraded_reasons.append("RERANK_UNAVAILABLE")
            return fused
        LOGGER.info(
            "retrieval rerank completed",
            extra={
                "system_id": str(system_id),
                "channel": "rerank",
                "candidate_count": len(candidates),
                "result_count": len(batch.results),
                "model": batch.model,
                "model_version": batch.model_version,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return tuple(
            replace(candidates[item.index], rerank_score=item.score) for item in batch.results
        )

    def _record_degradation(
        self,
        *,
        system_id: UUID,
        channel: str,
        reason: str,
    ) -> None:
        LOGGER.warning(
            "%s retrieval degraded",
            channel,
            extra={"system_id": str(system_id), "channel": channel, "reason": reason},
        )
        self._metrics.record_degradation(
            system_id=system_id,
            channel=channel,
            reason=reason,
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
                entry.fused_score += self._weights[channel] / (self._rrf_k + rank)
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
