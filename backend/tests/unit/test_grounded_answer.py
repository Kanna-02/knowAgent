from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.grounded_answer import GroundedAnswerService
from knowagent.agent.domain.models import GenerationEvent, GenerationRequest
from knowagent.common.errors import ValidationError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import FusedSearchHit, RetrievalResult, SearchHit


def fused_hit() -> FusedSearchHit:
    hit = SearchHit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text="发布前必须执行数据库迁移。",
        locators=(
            SourceLocator(
                document_id=uuid4(),
                document_version_id=uuid4(),
                source_type=SourceType.PDF,
                block_index=0,
                page_number=3,
            ),
        ),
        source_name="部署手册.pdf",
        source_version="2",
        score=0.9,
    )
    return FusedSearchHit.from_search_hit(
        hit,
        fused_score=0.03,
        channels=("keyword", "vector"),
    )


class StubRetrieval:
    def __init__(
        self,
        hits: tuple[FusedSearchHit, ...],
        *,
        degraded_reasons: tuple[str, ...] = (),
    ) -> None:
        self.hits = hits
        self.degraded_reasons = degraded_reasons
        self.system_id: UUID | None = None

    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult:
        self.system_id = system_id
        return RetrievalResult(
            query=query.strip(),
            hits=self.hits,
            degraded_reasons=self.degraded_reasons,
        )


class StubLlm:
    @property
    def model(self) -> str:
        return "qwen-test"

    @property
    def prompt_version(self) -> str:
        return "grounded-answer-v1"

    async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
        assert "[E1]" in request.evidence.prompt_text
        yield GenerationEvent.delta(
            json.dumps(
                {
                    "claims": [
                        {
                            "text": "发布前必须执行数据库迁移。",
                            "citations": [
                                {
                                    "evidence_id": "E1",
                                    "quote": "发布前必须执行数据库迁移。",
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        )
        yield GenerationEvent.completed()


def service(retrieval: StubRetrieval) -> GroundedAnswerService:
    return GroundedAnswerService(
        retrieval=retrieval,
        evidence=EvidenceOrganizer(max_items=3, max_characters=500),
        answers=AnswerGenerator(StubLlm()),
    )


@pytest.mark.asyncio
async def test_answer_runs_retrieval_evidence_generation_and_citation_validation() -> None:
    retrieval = StubRetrieval((fused_hit(),))
    system_id = uuid4()

    result = await service(retrieval).answer(system_id=system_id, question="如何发布？")

    assert result.answer.text == "发布前必须执行数据库迁移。"
    assert result.answer.citations[0].source_name == "部署手册.pdf"
    assert result.degraded_reasons == ()
    assert retrieval.system_id == system_id


@pytest.mark.asyncio
async def test_answer_preserves_vector_degradation_without_loosening_citations() -> None:
    retrieval = StubRetrieval((fused_hit(),), degraded_reasons=("VECTOR_UNAVAILABLE",))

    result = await service(retrieval).answer(system_id=uuid4(), question="如何发布？")

    assert result.degraded_reasons == ("VECTOR_UNAVAILABLE",)
    assert len(result.answer.citations) == 1


@pytest.mark.asyncio
async def test_answer_stops_before_llm_when_retrieval_has_no_evidence() -> None:
    retrieval = StubRetrieval(())

    with pytest.raises(ValidationError, match="没有可用于回答的证据"):
        await service(retrieval).answer(system_id=uuid4(), question="未知问题")
