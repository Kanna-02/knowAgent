from __future__ import annotations

from typing import Protocol
from uuid import UUID

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.domain.models import GroundedAnswer
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import RetrievalResult


class RetrievalService(Protocol):  # pylint: disable=too-few-public-methods
    async def retrieve(self, *, system_id: UUID, query: str) -> RetrievalResult: ...


class GroundedAnswerService:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        evidence: EvidenceOrganizer,
        answers: AnswerGenerator,
    ) -> None:
        self._retrieval = retrieval
        self._evidence = evidence
        self._answers = answers

    async def answer(self, *, system_id: UUID, question: str) -> GroundedAnswer:
        retrieval = await self._retrieval.retrieve(system_id=system_id, query=question)
        evidence = self._evidence.organize(retrieval.hits)
        answer = await self._answers.generate(question=retrieval.query, evidence=evidence)
        return GroundedAnswer(
            answer=answer,
            degraded_reasons=retrieval.degraded_reasons,
        )
