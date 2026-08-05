from __future__ import annotations

import collections.abc
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowagent.agent.application.answer_generation import (
    AnswerGenerator,
    StreamedAnswerCompleted,
    StreamedAnswerDelta,
)
from knowagent.agent.application.evidence_decision import (
    DeterministicEvidencePolicy,
    normalize_question,
)
from knowagent.agent.domain.models import (
    AnswerSnapshot,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    QuestionResolution,
    QuestionResolutionStatus,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.common.errors import ConflictError, ProviderUnavailableError, ValidationError
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import EvidenceBundle, RetrievalResult

GROUNDING_FAILURE_CODES = {
    "ANSWER_CITATION_REQUIRED",
    "ANSWER_CITATION_UNKNOWN",
    "ANSWER_CITATION_UNSUPPORTED",
    "ANSWER_CLAIM_UNSUPPORTED",
}


class RetrievalService(Protocol):  # pylint: disable=too-few-public-methods
    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult: ...


class ResolutionRecorder(Protocol):
    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None: ...

    def record_sufficient(self, *, decision: EvidenceDecision) -> None: ...

    def create_from_refusal(
        self,
        *,
        decision: EvidenceDecision,
        requester_id: UUID,
        now: datetime,
    ) -> UUID: ...


class AnswerRecorder(Protocol):  # pylint: disable=too-few-public-methods
    def get_by_run(self, *, system_id: UUID, run_id: UUID) -> AnswerSnapshot | None: ...

    def record(
        self,
        *,
        decision: EvidenceDecision,
        answer: VerifiedAnswer,
        degraded_reasons: tuple[str, ...],
        now: datetime,
    ) -> AnswerSnapshot: ...


class ReliableQuestionService:  # pylint: disable=too-few-public-methods,too-many-instance-attributes,too-many-arguments
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        evidence: EvidenceOrganizer,
        policy: DeterministicEvidencePolicy,
        answers: AnswerGenerator,
        recorder: ResolutionRecorder,
        snapshots: AnswerRecorder,
        clock: Callable[[], datetime],
    ) -> None:
        self._retrieval = retrieval
        self._evidence = evidence
        self._policy = policy
        self._answers = answers
        self._recorder = recorder
        self._snapshots = snapshots
        self._clock = clock

    async def resolve(
        self,
        *,
        run_id: UUID,
        requester_id: UUID,
        system_id: UUID,
        question: str,
        required_terms: tuple[str, ...] = (),
    ) -> QuestionResolution:
        replay = self._replay_answer(run_id=run_id, system_id=system_id, question=question)
        if replay is not None:
            return replay
        retrieval = await self._retrieval.retrieve(system_id=system_id, query=question)
        now = self._clock()
        decision = self._policy.decide(
            run_id=run_id,
            system_id=system_id,
            retrieval=retrieval,
            decided_at=now,
            required_terms=required_terms,
        )
        if decision.outcome.is_refusal:
            return self._record_refusal(
                decision=decision,
                requester_id=requester_id,
                now=now,
            )

        evidence = self._evidence.organize(retrieval.hits)
        if not evidence.items:
            refused = replace(
                decision,
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                reason_codes=(EvidenceReasonCode.EVIDENCE_BUDGET_EMPTY,),
            )
            return self._record_refusal(
                decision=refused,
                requester_id=requester_id,
                now=now,
            )
        try:
            answer = await self._answers.generate(question=retrieval.query, evidence=evidence)
        except ValidationError as error:
            if error.code not in GROUNDING_FAILURE_CODES:
                if error.code.startswith("ANSWER_"):
                    raise ProviderUnavailableError("llm") from error
                raise
            refused = replace(
                decision,
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                reason_codes=(EvidenceReasonCode.ANSWER_NOT_GROUNDED,),
            )
            return self._record_refusal(
                decision=refused,
                requester_id=requester_id,
                now=now,
            )

        self._recorder.record_sufficient(decision=decision)
        self._snapshots.record(
            decision=decision,
            answer=answer,
            degraded_reasons=retrieval.degraded_reasons,
            now=now,
        )
        return QuestionResolution(
            status=QuestionResolutionStatus.ANSWERED,
            decision=decision,
            answer=answer,
            ticket_id=None,
            reason_codes=(),
            degraded_reasons=retrieval.degraded_reasons,
        )

    async def resolve_stream(
        self,
        *,
        run_id: UUID,
        requester_id: UUID,
        system_id: UUID,
        question: str,
        required_terms: tuple[str, ...] = (),
    ) -> collections.abc.AsyncIterator[QuestionStreamEvent]:
        """Yield typed stream events for the SSE endpoint.

        Mirrors :meth:`resolve` but emits incremental events: retrieval
        start, evidence bundle, decision, token deltas and the final
        grounded answer (or a refusal with the created ticket id). The
        non-stream ``resolve`` is preserved for request/replay callers.
        """
        replay = self._replay_answer(run_id=run_id, system_id=system_id, question=question)
        if replay is not None:
            if replay.answer is not None:
                yield QuestionStreamEvent(
                    kind=QuestionStreamEventKind.ANSWER_COMPLETED,
                    payload=replay.answer,
                    run_id=run_id,
                    degraded_reasons=replay.degraded_reasons,
                )
            else:
                yield QuestionStreamEvent(
                    kind=QuestionStreamEventKind.REFUSED,
                    payload=replay.decision,
                    run_id=run_id,
                )
            return

        yield QuestionStreamEvent(
            kind=QuestionStreamEventKind.RETRIEVAL_STARTED,
            payload=None,
            run_id=run_id,
        )
        retrieval = await self._retrieval.retrieve(system_id=system_id, query=question)
        now = self._clock()
        decision = self._policy.decide(
            run_id=run_id,
            system_id=system_id,
            retrieval=retrieval,
            decided_at=now,
            required_terms=required_terms,
        )
        if decision.outcome.is_refusal:
            refusal = self._record_refusal(
                decision=decision,
                requester_id=requester_id,
                now=now,
            )
            yield QuestionStreamEvent(
                kind=QuestionStreamEventKind.REFUSED,
                payload=refusal.decision,
                run_id=run_id,
            )
            return

        evidence = self._evidence.organize(retrieval.hits)
        yield QuestionStreamEvent(
            kind=QuestionStreamEventKind.EVIDENCE_READY,
            payload=evidence,
            run_id=run_id,
            degraded_reasons=retrieval.degraded_reasons,
        )
        if not evidence.items:
            refused_decision = replace(
                decision,
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                reason_codes=(EvidenceReasonCode.EVIDENCE_BUDGET_EMPTY,),
            )
            refusal = self._record_refusal(
                decision=refused_decision,
                requester_id=requester_id,
                now=now,
            )
            yield QuestionStreamEvent(
                kind=QuestionStreamEventKind.REFUSED,
                payload=refusal.decision,
                run_id=run_id,
            )
            return

        yield QuestionStreamEvent(
            kind=QuestionStreamEventKind.DECISION,
            payload=decision,
            run_id=run_id,
        )
        try:
            async for streamed in self._answers.generate_stream(
                question=retrieval.query, evidence=evidence
            ):
                if isinstance(streamed, StreamedAnswerDelta):
                    yield QuestionStreamEvent(
                        kind=QuestionStreamEventKind.ANSWER_DELTA,
                        payload=streamed.text,
                        run_id=run_id,
                    )
                    continue
                assert isinstance(streamed, StreamedAnswerCompleted)
                self._recorder.record_sufficient(decision=decision)
                self._snapshots.record(
                    decision=decision,
                    answer=streamed.answer,
                    degraded_reasons=retrieval.degraded_reasons,
                    now=now,
                )
                yield QuestionStreamEvent(
                    kind=QuestionStreamEventKind.ANSWER_COMPLETED,
                    payload=streamed.answer,
                    run_id=run_id,
                    degraded_reasons=retrieval.degraded_reasons,
                )
        except ValidationError as error:
            if error.code not in GROUNDING_FAILURE_CODES:
                if error.code.startswith("ANSWER_"):
                    raise ProviderUnavailableError("llm") from error
                raise
            refused_decision = replace(
                decision,
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                reason_codes=(EvidenceReasonCode.ANSWER_NOT_GROUNDED,),
            )
            refusal = self._record_refusal(
                decision=refused_decision,
                requester_id=requester_id,
                now=now,
            )
            yield QuestionStreamEvent(
                kind=QuestionStreamEventKind.REFUSED,
                payload=refusal.decision,
                run_id=run_id,
            )

    def _replay_answer(
        self,
        *,
        run_id: UUID,
        system_id: UUID,
        question: str,
    ) -> QuestionResolution | None:
        snapshot = self._snapshots.get_by_run(system_id=system_id, run_id=run_id)
        if snapshot is None:
            return None
        decision = self._recorder.get_decision(run_id=run_id)
        if decision is None or decision.system_id != system_id:
            raise ConflictError("QUESTION_RUN_INCONSISTENT", "问答运行记录与答案快照不一致")
        if decision.normalized_query != normalize_question(question):
            raise ConflictError("QUESTION_RUN_REUSED", "同一问答运行的问题不一致")
        return QuestionResolution(
            status=QuestionResolutionStatus.ANSWERED,
            decision=decision,
            answer=snapshot.answer,
            ticket_id=None,
            reason_codes=(),
            degraded_reasons=snapshot.degraded_reasons,
        )

    def _record_refusal(
        self,
        *,
        decision: EvidenceDecision,
        requester_id: UUID,
        now: datetime,
    ) -> QuestionResolution:
        ticket_id = self._recorder.create_from_refusal(
            decision=decision,
            requester_id=requester_id,
            now=now,
        )
        recorded_decision = replace(decision, ticket_id=ticket_id)
        return QuestionResolution(
            status=QuestionResolutionStatus.REFUSED,
            decision=recorded_decision,
            answer=None,
            ticket_id=ticket_id,
            reason_codes=decision.reason_codes,
            degraded_reasons=decision.degraded_reasons,
        )
