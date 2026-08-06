from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.application.retrieval_service import BasicRetrievalService
from knowagent.retrieval.domain.models import (
    EmbeddingBatch,
    RerankBatch,
    RerankScore,
    SearchHit,
)


def locator() -> SourceLocator:
    return SourceLocator(
        document_id=uuid4(),
        document_version_id=uuid4(),
        source_type=SourceType.MARKDOWN,
        block_index=0,
        heading_path=("部署",),
        paragraph_start=1,
        paragraph_end=1,
        line_start=3,
        line_end=5,
    )


def hit(chunk_id: UUID, *, score: float, text: str = "部署前执行数据库迁移。") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        source_id=uuid4(),
        text=text,
        locators=(locator(),),
        source_name="部署手册.md",
        source_version="v2",
        score=score,
    )


class StubEmbeddingProvider:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch:
        if self.unavailable:
            raise ProviderUnavailableError("embedding")
        assert texts == ("如何部署？",)
        return EmbeddingBatch(
            model="bge-m3",
            model_version="2026-08",
            dimension=3,
            normalized=True,
            vectors=((0.1, 0.2, 0.3),),
        )


class StubLexicalSearch:
    def __init__(self, results: tuple[SearchHit, ...]) -> None:
        self.results = results
        self.system_ids: list[UUID] = []

    def search(self, *, system_id: UUID, query: str, limit: int) -> tuple[SearchHit, ...]:
        self.system_ids.append(system_id)
        assert query == "如何部署？"
        assert limit == 3
        return self.results


class StubVectorSearch:
    def __init__(self, results: tuple[SearchHit, ...], *, unavailable: bool = False) -> None:
        self.results = results
        self.unavailable = unavailable
        self.calls = 0

    def search_vectors(
        self,
        *,
        system_id: UUID,
        vector: tuple[float, ...],
        model: str,
        model_version: str,
        limit: int,
    ) -> tuple[SearchHit, ...]:
        del system_id
        self.calls += 1
        if self.unavailable:
            raise ProviderUnavailableError("vector_search")
        assert vector == (0.1, 0.2, 0.3)
        assert (model, model_version, limit) == ("bge-m3", "2026-08", 3)
        return self.results


class StubRetrievalMetrics:
    def __init__(self) -> None:
        self.degradations: list[tuple[UUID, str, str]] = []

    def record_degradation(self, *, system_id: UUID, channel: str, reason: str) -> None:
        self.degradations.append((system_id, channel, reason))


class StubRerankProvider:
    def __init__(
        self,
        *,
        scores: tuple[RerankScore, ...] = (),
        unavailable: bool = False,
    ) -> None:
        self.scores = scores
        self.unavailable = unavailable
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    async def rerank(
        self,
        *,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch:
        self.calls.append((query, documents, top_k))
        if self.unavailable:
            raise ProviderUnavailableError("rerank")
        return RerankBatch(
            model="BAAI/bge-reranker-v2-m3",
            model_version="revision-1",
            results=self.scores,
        )


@pytest.mark.anyio
async def test_retrieve_fuses_keyword_and_vector_ranks_without_duplicates() -> None:
    shared_id, lexical_only_id, vector_only_id = uuid4(), uuid4(), uuid4()
    lexical = StubLexicalSearch((hit(shared_id, score=0.9), hit(lexical_only_id, score=0.8)))
    vector = StubVectorSearch((hit(vector_only_id, score=0.95), hit(shared_id, score=0.85)))
    metrics = StubRetrievalMetrics()
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(),
        lexical=lexical,
        vectors=vector,
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=3,
        rrf_k=60,
        metrics=metrics,
    )
    system_id = uuid4()

    result = await service.retrieve(system_id=system_id, query="  如何部署？  ")

    assert [item.chunk_id for item in result.hits] == [shared_id, vector_only_id, lexical_only_id]
    assert result.hits[0].channels == ("keyword", "vector")
    assert result.degraded_reasons == ()
    assert lexical.system_ids == [system_id]
    assert metrics.degradations == []


@pytest.mark.anyio
async def test_retrieve_falls_back_to_keyword_when_embedding_is_unavailable() -> None:
    keyword_hit = hit(uuid4(), score=0.75)
    vectors = StubVectorSearch(())
    metrics = StubRetrievalMetrics()
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(unavailable=True),
        lexical=StubLexicalSearch((keyword_hit,)),
        vectors=vectors,
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=3,
        rrf_k=60,
        metrics=metrics,
    )

    system_id = uuid4()

    result = await service.retrieve(system_id=system_id, query="如何部署？")

    assert [item.chunk_id for item in result.hits] == [keyword_hit.chunk_id]
    assert result.hits[0].channels == ("keyword",)
    assert result.degraded_reasons == ("VECTOR_UNAVAILABLE",)
    assert vectors.calls == 0
    assert metrics.degradations == [(system_id, "vector", "embedding_unavailable")]


@pytest.mark.anyio
async def test_retrieve_falls_back_and_records_metric_when_vector_search_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    keyword_hit = hit(uuid4(), score=0.75)
    metrics = StubRetrievalMetrics()
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(),
        lexical=StubLexicalSearch((keyword_hit,)),
        vectors=StubVectorSearch((), unavailable=True),
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=3,
        rrf_k=60,
        metrics=metrics,
    )
    system_id = uuid4()

    result = await service.retrieve(system_id=system_id, query="如何部署？")

    assert [item.chunk_id for item in result.hits] == [keyword_hit.chunk_id]
    assert result.degraded_reasons == ("VECTOR_UNAVAILABLE",)
    assert metrics.degradations == [(system_id, "vector", "vector_search_unavailable")]
    assert "vector retrieval degraded" in caplog.text


@pytest.mark.anyio
async def test_retrieve_rejects_blank_query_without_calling_providers() -> None:
    vectors = StubVectorSearch(())
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(),
        lexical=StubLexicalSearch(()),
        vectors=vectors,
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=3,
        rrf_k=60,
        metrics=StubRetrievalMetrics(),
    )

    with pytest.raises(ValidationError, match="问题不能为空"):
        await service.retrieve(system_id=uuid4(), query="   ")

    assert vectors.calls == 0


@pytest.mark.anyio
async def test_retrieve_applies_weighted_rrf_before_reranking() -> None:
    keyword_id, vector_id = uuid4(), uuid4()
    reranker = StubRerankProvider(
        scores=(RerankScore(index=1, score=0.9), RerankScore(index=0, score=0.2))
    )
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(),
        lexical=StubLexicalSearch((hit(keyword_id, score=0.9),)),
        vectors=StubVectorSearch((hit(vector_id, score=0.95),)),
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=2,
        rrf_k=60,
        metrics=StubRetrievalMetrics(),
        reranker=reranker,
        rerank_candidate_top_k=2,
        rerank_top_k=2,
        keyword_weight=2.0,
        vector_weight=1.0,
    )

    result = await service.retrieve(system_id=uuid4(), query="如何部署？")

    assert [item.chunk_id for item in result.hits] == [vector_id, keyword_id]
    assert result.hits[0].rerank_score == 0.9
    assert result.hits[1].rerank_score == 0.2
    assert result.hits[1].fused_score > result.hits[0].fused_score
    assert reranker.calls == [
        ("如何部署？", ("部署前执行数据库迁移。", "部署前执行数据库迁移。"), 2)
    ]
    assert result.degraded_reasons == ()


@pytest.mark.anyio
async def test_retrieve_falls_back_to_weighted_fusion_when_rerank_is_unavailable() -> None:
    shared_id, vector_only_id = uuid4(), uuid4()
    metrics = StubRetrievalMetrics()
    reranker = StubRerankProvider(unavailable=True)
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(),
        lexical=StubLexicalSearch((hit(shared_id, score=0.9),)),
        vectors=StubVectorSearch((hit(vector_only_id, score=0.95), hit(shared_id, score=0.85))),
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=2,
        rrf_k=60,
        metrics=metrics,
        reranker=reranker,
        rerank_candidate_top_k=2,
        rerank_top_k=2,
    )
    system_id = uuid4()

    result = await service.retrieve(system_id=system_id, query="如何部署？")

    assert [item.chunk_id for item in result.hits] == [shared_id, vector_only_id]
    assert result.degraded_reasons == ("RERANK_UNAVAILABLE",)
    assert metrics.degradations == [(system_id, "rerank", "rerank_unavailable")]


@pytest.mark.anyio
async def test_retrieve_preserves_vector_and_rerank_degradations_together() -> None:
    keyword_hit = hit(uuid4(), score=0.75)
    metrics = StubRetrievalMetrics()
    service = BasicRetrievalService(
        embeddings=StubEmbeddingProvider(unavailable=True),
        lexical=StubLexicalSearch((keyword_hit,)),
        vectors=StubVectorSearch(()),
        keyword_top_k=3,
        vector_top_k=3,
        result_top_k=1,
        rrf_k=60,
        metrics=metrics,
        reranker=StubRerankProvider(unavailable=True),
        rerank_candidate_top_k=1,
        rerank_top_k=1,
    )
    system_id = uuid4()

    result = await service.retrieve(system_id=system_id, query="如何部署？")

    assert result.hits[0].chunk_id == keyword_hit.chunk_id
    assert result.degraded_reasons == ("VECTOR_UNAVAILABLE", "RERANK_UNAVAILABLE")
    assert metrics.degradations == [
        (system_id, "vector", "embedding_unavailable"),
        (system_id, "rerank", "rerank_unavailable"),
    ]
