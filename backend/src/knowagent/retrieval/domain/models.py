from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from knowagent.documents.domain.models import SourceLocator

RetrievalChannel = str


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    model: str
    model_version: str
    dimension: int
    normalized: bool
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.model_version.strip():
            raise ValueError("embedding model metadata must not be blank")
        if self.dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        if not self.vectors:
            raise ValueError("embedding vectors must not be empty")
        for vector in self.vectors:
            if len(vector) != self.dimension:
                raise ValueError("embedding vector dimension does not match metadata")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("embedding vector values must be finite")


@dataclass(frozen=True, slots=True)
class RerankScore:
    index: int
    score: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("rerank result index must not be negative")
        if not math.isfinite(self.score):
            raise ValueError("rerank score must be finite")


@dataclass(frozen=True, slots=True)
class RerankBatch:
    model: str
    model_version: str
    results: tuple[RerankScore, ...]

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.model_version.strip():
            raise ValueError("rerank model metadata must not be blank")
        if not self.results:
            raise ValueError("rerank results must not be empty")
        indexes = tuple(result.index for result in self.results)
        scores = tuple(result.score for result in self.results)
        if len(set(indexes)) != len(indexes):
            raise ValueError("rerank result indexes must be unique")
        if scores != tuple(sorted(scores, reverse=True)):
            raise ValueError("rerank results must be ordered by descending score")


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: UUID
    source_id: UUID
    text: str
    locators: tuple[SourceLocator, ...]
    source_name: str
    source_version: str
    score: float

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("search hit text must not be blank")
        if not self.source_name.strip() or not self.source_version.strip():
            raise ValueError("search hit source metadata must not be blank")
        if not math.isfinite(self.score):
            raise ValueError("search hit score must be finite")


@dataclass(frozen=True, slots=True)
class FusedSearchHit(SearchHit):
    fused_score: float
    channels: tuple[RetrievalChannel, ...]
    rerank_score: float | None = None

    @classmethod
    def from_search_hit(
        cls,
        hit: SearchHit,
        *,
        fused_score: float,
        channels: tuple[RetrievalChannel, ...],
    ) -> FusedSearchHit:
        if not channels:
            raise ValueError("fused search hit must include at least one channel")
        return cls(
            chunk_id=hit.chunk_id,
            source_id=hit.source_id,
            text=hit.text,
            locators=hit.locators,
            source_name=hit.source_name,
            source_version=hit.source_version,
            score=hit.score,
            fused_score=fused_score,
            channels=channels,
        )


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    hits: tuple[FusedSearchHit, ...]
    degraded_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    chunk_id: UUID
    source_id: UUID
    quoted_text: str
    source_name: str
    source_version: str
    locators: tuple[SourceLocator, ...]


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    items: tuple[EvidenceItem, ...]
    prompt_text: str
