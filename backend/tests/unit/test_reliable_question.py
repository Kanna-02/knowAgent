from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.models import (
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    GenerationEvent,
    GenerationRequest,
    QuestionResolutionStatus,
)
from knowagent.common.errors import ProviderUnavailableError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import FusedSearchHit, RetrievalResult, SearchHit

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def make_hit() -> FusedSearchHit:
    raw = SearchHit(
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
        raw,
        fused_score=0.03,
        channels=("keyword", "vector"),
    )


class StubRetrieval:
    def __init__(self, result: RetrievalResult | Exception) -> None:
        self.result = result

    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult:
        del system_id, query
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class StubLlm:
    def __init__(
        self,
        *,
        invalid_citation: bool = False,
        malformed: bool = False,
        unavailable: bool = False,
    ) -> None:
        self.invalid_citation = invalid_citation
        self.malformed = malformed
        self.unavailable = unavailable
        self.calls = 0

    @property
    def model(self) -> str:
        return "qwen-test"

    @property
    def prompt_version(self) -> str:
        return "grounded-answer-v1"

    async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
        self.calls += 1
        if self.unavailable:
            raise ProviderUnavailableError("llm")
        if self.malformed:
            yield GenerationEvent.delta("not-json")
            yield GenerationEvent.completed()
            return
        quote = (
            "不存在于证据中的内容"
            if self.invalid_citation
            else request.evidence.items[0].quoted_text
        )
        yield GenerationEvent.delta(
            json.dumps(
                {
                    "claims": [
                        {
                            "text": quote,
                            "citations": [{"evidence_id": "E1", "quote": quote}],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        yield GenerationEvent.completed()


class RecordingResolutionRecorder:
    def __init__(self) -> None:
        self.sufficient: list[EvidenceDecision] = []
        self.refusals: list[EvidenceDecision] = []
        self.ticket_id = uuid4()

    def record_sufficient(self, *, decision: EvidenceDecision) -> None:
        self.sufficient.append(decision)

    def create_from_refusal(
        self,
        *,
        decision: EvidenceDecision,
        requester_id: UUID,
        now: datetime,
    ) -> UUID:
        del requester_id, now
        self.refusals.append(decision)
        return self.ticket_id


def service(
    *,
    retrieval: StubRetrieval,
    llm: StubLlm,
    recorder: RecordingResolutionRecorder,
    evidence_max_characters: int = 500,
) -> ReliableQuestionService:
    return ReliableQuestionService(
        retrieval=retrieval,
        evidence=EvidenceOrganizer(max_items=3, max_characters=evidence_max_characters),
        policy=DeterministicEvidencePolicy(
            policy_version="evidence-v1",
            minimum_fused_score=0.015,
            minimum_score_gap=0.0,
            degraded_score_multiplier=1.2,
        ),
        answers=AnswerGenerator(llm),
        recorder=recorder,
        clock=lambda: NOW,
    )


@pytest.mark.anyio
async def test_resolve_with_sufficient_evidence_returns_verified_answer() -> None:
    recorder = RecordingResolutionRecorder()
    llm = StubLlm()
    result = await service(
        retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
        llm=llm,
        recorder=recorder,
    ).resolve(
        run_id=uuid4(),
        requester_id=uuid4(),
        system_id=uuid4(),
        question="如何发布？",
    )

    assert result.status is QuestionResolutionStatus.ANSWERED
    assert result.answer is not None
    assert result.answer.text == "发布前必须执行数据库迁移。"
    assert result.ticket_id is None
    assert recorder.sufficient[0].outcome is EvidenceDecisionOutcome.SUFFICIENT
    assert recorder.refusals == []


@pytest.mark.anyio
async def test_resolve_without_evidence_refuses_and_creates_ticket_without_calling_llm() -> None:
    recorder = RecordingResolutionRecorder()
    llm = StubLlm()
    result = await service(
        retrieval=StubRetrieval(RetrievalResult(query="未知问题", hits=())),
        llm=llm,
        recorder=recorder,
    ).resolve(
        run_id=uuid4(),
        requester_id=uuid4(),
        system_id=uuid4(),
        question="未知问题",
    )

    assert result.status is QuestionResolutionStatus.REFUSED
    assert result.answer is None
    assert result.ticket_id == recorder.ticket_id
    assert result.reason_codes == (EvidenceReasonCode.NO_EVIDENCE,)
    assert llm.calls == 0


@pytest.mark.anyio
async def test_resolve_with_unverifiable_generated_claim_refuses_and_creates_ticket() -> None:
    recorder = RecordingResolutionRecorder()
    result = await service(
        retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
        llm=StubLlm(invalid_citation=True),
        recorder=recorder,
    ).resolve(
        run_id=uuid4(),
        requester_id=uuid4(),
        system_id=uuid4(),
        question="如何发布？",
    )

    assert result.status is QuestionResolutionStatus.REFUSED
    assert result.reason_codes == (EvidenceReasonCode.ANSWER_NOT_GROUNDED,)
    assert recorder.refusals[0].outcome is EvidenceDecisionOutcome.INSUFFICIENT


@pytest.mark.anyio
async def test_resolve_when_evidence_budget_excludes_every_hit_refuses_before_llm() -> None:
    recorder = RecordingResolutionRecorder()
    llm = StubLlm()
    result = await service(
        retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
        llm=llm,
        recorder=recorder,
        evidence_max_characters=5,
    ).resolve(
        run_id=uuid4(),
        requester_id=uuid4(),
        system_id=uuid4(),
        question="如何发布？",
    )

    assert result.status is QuestionResolutionStatus.REFUSED
    assert result.reason_codes == (EvidenceReasonCode.EVIDENCE_BUDGET_EMPTY,)
    assert llm.calls == 0


@pytest.mark.anyio
async def test_resolve_when_llm_returns_invalid_format_does_not_create_ticket() -> None:
    recorder = RecordingResolutionRecorder()

    with pytest.raises(ProviderUnavailableError):
        await service(
            retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
            llm=StubLlm(malformed=True),
            recorder=recorder,
        ).resolve(
            run_id=uuid4(),
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )

    assert recorder.sufficient == []
    assert recorder.refusals == []


@pytest.mark.anyio
async def test_resolve_when_llm_unavailable_propagates_system_failure_without_ticket() -> None:
    recorder = RecordingResolutionRecorder()

    with pytest.raises(ProviderUnavailableError):
        await service(
            retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
            llm=StubLlm(unavailable=True),
            recorder=recorder,
        ).resolve(
            run_id=uuid4(),
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )

    assert recorder.sufficient == []
    assert recorder.refusals == []


@pytest.mark.anyio
async def test_resolve_when_retrieval_unavailable_propagates_system_failure_without_ticket() -> (
    None
):
    recorder = RecordingResolutionRecorder()

    with pytest.raises(ProviderUnavailableError):
        await service(
            retrieval=StubRetrieval(ProviderUnavailableError("database")),
            llm=StubLlm(),
            recorder=recorder,
        ).resolve(
            run_id=uuid4(),
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )

    assert recorder.sufficient == []
    assert recorder.refusals == []
