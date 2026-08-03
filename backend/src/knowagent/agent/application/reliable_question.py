from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.domain.models import (
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    QuestionResolution,
    QuestionResolutionStatus,
)
from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import RetrievalResult

GROUNDING_FAILURE_CODES = {
    "ANSWER_CITATION_REQUIRED",
    "ANSWER_CITATION_UNKNOWN",
    "ANSWER_CITATION_UNSUPPORTED",
    "ANSWER_CLAIM_UNSUPPORTED",
}


class RetrievalService(Protocol):  # pylint: disable=too-few-public-methods
    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult: ...


class ResolutionRecorder(Protocol):
    def record_sufficient(self, *, decision: EvidenceDecision) -> None: ...

    def create_from_refusal(
        self,
        *,
        decision: EvidenceDecision,
        requester_id: UUID,
        now: datetime,
    ) -> UUID: ...


class ReliableQuestionService:  # pylint: disable=too-few-public-methods,too-many-instance-attributes,too-many-arguments
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        evidence: EvidenceOrganizer,
        policy: DeterministicEvidencePolicy,
        answers: AnswerGenerator,
        recorder: ResolutionRecorder,
        clock: Callable[[], datetime],
    ) -> None:
        self._retrieval = retrieval
        self._evidence = evidence
        self._policy = policy
        self._answers = answers
        self._recorder = recorder
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
        return QuestionResolution(
            status=QuestionResolutionStatus.ANSWERED,
            decision=decision,
            answer=answer,
            ticket_id=None,
            reason_codes=(),
            degraded_reasons=retrieval.degraded_reasons,
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
