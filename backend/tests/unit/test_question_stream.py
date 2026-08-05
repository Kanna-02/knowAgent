from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.models import (
    AnswerSnapshot,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    GenerationEvent,
    GenerationRequest,
    QuestionResolutionStatus,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.common.errors import ProviderUnavailableError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import (
    FusedSearchHit,
    RetrievalResult,
    SearchHit,
)

NOW = datetime(2026, 8, 4, 12, tzinfo=UTC)


def make_hit(*, score: float = 0.03, text: str = "发布前必须执行数据库迁移。") -> FusedSearchHit:
    raw = SearchHit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text=text,
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
    return FusedSearchHit.from_search_hit(raw, fused_score=score, channels=("keyword", "vector"))


class StubRetrieval:
    def __init__(self, result: RetrievalResult | Exception) -> None:
        self.result: RetrievalResult | Exception = result
        self.calls = 0

    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult:
        del system_id, query
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class StubLlm:
    def __init__(self, *, unavailable: bool = False, invalid: bool = False) -> None:
        self.unavailable = unavailable
        self.invalid = invalid
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
        quote = "不存在于证据中的内容" if self.invalid else request.evidence.items[0].quoted_text
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


class RecordingRecorder:
    def __init__(self) -> None:
        self.sufficient: list[EvidenceDecision] = []
        self.refusals: list[EvidenceDecision] = []
        self.answers: list[tuple[EvidenceDecision, VerifiedAnswer, tuple[str, ...], datetime]] = []
        self.snapshots: dict[tuple[UUID, UUID], AnswerSnapshot] = {}
        self.ticket_id = uuid4()

    def record_sufficient(self, *, decision: EvidenceDecision) -> None:
        self.sufficient.append(decision)

    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None:
        return next((d for d in self.sufficient if d.run_id == run_id), None)

    def create_from_refusal(
        self, *, decision: EvidenceDecision, requester_id: UUID, now: datetime
    ) -> UUID:
        del requester_id, now
        self.refusals.append(decision)
        return self.ticket_id

    def record(
        self,
        *,
        decision: EvidenceDecision,
        answer: VerifiedAnswer,
        degraded_reasons: tuple[str, ...],
        now: datetime,
    ) -> AnswerSnapshot:
        self.answers.append((decision, answer, degraded_reasons, now))
        snap = AnswerSnapshot(
            id=uuid4(),
            run_id=decision.run_id,
            system_id=decision.system_id,
            answer=answer,
            degraded_reasons=degraded_reasons,
            created_at=now,
        )
        self.snapshots[(decision.system_id, decision.run_id)] = snap
        return snap

    def get_by_run(self, *, system_id: UUID, run_id: UUID) -> AnswerSnapshot | None:
        return self.snapshots.get((system_id, run_id))


def service(
    *, retrieval: StubRetrieval, llm: StubLlm, recorder: RecordingRecorder
) -> ReliableQuestionService:
    return ReliableQuestionService(
        retrieval=retrieval,
        evidence=EvidenceOrganizer(max_items=3, max_characters=500),
        policy=DeterministicEvidencePolicy(
            policy_version="evidence-v1",
            minimum_fused_score=0.015,
            minimum_score_gap=0.0,
            degraded_score_multiplier=1.2,
        ),
        answers=AnswerGenerator(llm),
        recorder=recorder,
        snapshots=recorder,
        clock=lambda: NOW,
    )


async def _collect_events(stream) -> list[QuestionStreamEvent]:
    return [event async for event in stream]


@pytest.mark.anyio
async def test_resolve_stream_emits_full_answer_sequence() -> None:
    recorder = RecordingRecorder()
    run_id = uuid4()
    events = await _collect_events(
        service(
            retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
            llm=StubLlm(),
            recorder=recorder,
        ).resolve_stream(
            run_id=run_id,
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )
    )
    kinds = [e.kind for e in events]
    assert kinds == [
        QuestionStreamEventKind.RETRIEVAL_STARTED,
        QuestionStreamEventKind.EVIDENCE_READY,
        QuestionStreamEventKind.DECISION,
        QuestionStreamEventKind.ANSWER_DELTA,
        QuestionStreamEventKind.ANSWER_COMPLETED,
    ]
    assert events[0].run_id == run_id
    completed = events[-1]
    assert isinstance(completed.payload, VerifiedAnswer)
    assert completed.payload.text == "发布前必须执行数据库迁移。"
    assert recorder.sufficient and recorder.answers
    assert not recorder.refusals


@pytest.mark.anyio
async def test_resolve_stream_refusal_after_empty_evidence_budget() -> None:
    recorder = RecordingRecorder()
    run_id = uuid4()
    # Non-empty hits but text exceeds the evidence character budget: the
    # policy allows the retrieval but EvidenceOrganizer drops every candidate,
    # so evidence is empty and the decision is downgraded to a refusal.
    big_hit = make_hit(text="A" * 2000)
    events = await _collect_events(
        service(
            retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(big_hit,))),
            llm=StubLlm(),
            recorder=recorder,
        ).resolve_stream(
            run_id=run_id,
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )
    )
    kinds = [e.kind for e in events]
    assert kinds == [
        QuestionStreamEventKind.RETRIEVAL_STARTED,
        QuestionStreamEventKind.EVIDENCE_READY,
        QuestionStreamEventKind.REFUSED,
    ]
    refused = events[-1]
    decision = refused.payload
    assert isinstance(decision, EvidenceDecision)
    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.ticket_id == recorder.ticket_id
    assert not recorder.answers
    assert recorder.refusals


@pytest.mark.anyio
async def test_resolve_stream_decision_refusal_short_circuits_before_evidence() -> None:
    recorder = RecordingRecorder()
    run_id = uuid4()
    # Hit below the policy threshold → decision refuses before evidence emitted.
    events = await _collect_events(
        service(
            retrieval=StubRetrieval(
                RetrievalResult(query="如何发布？", hits=(make_hit(score=0.001),))
            ),
            llm=StubLlm(),
            recorder=recorder,
        ).resolve_stream(
            run_id=run_id,
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        )
    )
    kinds = [e.kind for e in events]
    assert kinds == [
        QuestionStreamEventKind.RETRIEVAL_STARTED,
        QuestionStreamEventKind.REFUSED,
    ]
    assert events[-1].payload.outcome is EvidenceDecisionOutcome.INSUFFICIENT


@pytest.mark.anyio
async def test_resolve_stream_replays_stored_answer_without_external_calls() -> None:
    recorder = RecordingRecorder()
    run_id = uuid4()
    system_id = uuid4()
    # First call seeds a snapshot and a sufficient decision record.
    seeded = await service(
        retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
        llm=StubLlm(),
        recorder=recorder,
    ).resolve(
        run_id=run_id,
        requester_id=uuid4(),
        system_id=system_id,
        question="如何发布？",
    )
    assert seeded.status is QuestionResolutionStatus.ANSWERED
    # Second stream call reuses the same run_id and question → replay.
    retrieval = StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),)))
    llm = StubLlm()
    events = await _collect_events(
        service(
            retrieval=retrieval,
            llm=llm,
            recorder=recorder,
        ).resolve_stream(
            run_id=run_id,
            requester_id=uuid4(),
            system_id=system_id,
            question="如何发布？",
        )
    )
    kinds = [e.kind for e in events]
    assert kinds == [QuestionStreamEventKind.ANSWER_COMPLETED]
    completed = events[-1]
    assert isinstance(completed.payload, VerifiedAnswer)
    assert retrieval.calls == 0
    assert llm.calls == 0


@pytest.mark.anyio
async def test_resolve_stream_provider_unavailable_propagates() -> None:
    recorder = RecordingRecorder()
    run_id = uuid4()
    # Hit is sufficient so we reach the LLM, which raises provider-unavailable.
    svc = service(
        retrieval=StubRetrieval(RetrievalResult(query="如何发布？", hits=(make_hit(),))),
        llm=StubLlm(unavailable=True),
        recorder=recorder,
    )
    with pytest.raises(ProviderUnavailableError):
        async for _ in svc.resolve_stream(
            run_id=run_id,
            requester_id=uuid4(),
            system_id=uuid4(),
            question="如何发布？",
        ):
            pass
    # The retrieval and decision happened, but no answer recorded.
    assert not recorder.answers
