from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from knowagent.agent.domain.models import (
    AnswerSnapshot,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    VerifiedAnswer,
)
from knowagent.agent.ports import AnswerSnapshotRepository
from knowagent.common.errors import ConflictError, ValidationError


class AnswerSnapshotService:
    def __init__(self, *, repository: AnswerSnapshotRepository) -> None:
        self._repository = repository

    def record(
        self,
        *,
        decision: EvidenceDecision,
        answer: VerifiedAnswer,
        degraded_reasons: tuple[str, ...],
        now: datetime,
    ) -> AnswerSnapshot:
        if decision.outcome is not EvidenceDecisionOutcome.SUFFICIENT:
            raise ValidationError("ANSWER_SNAPSHOT_REQUIRES_ANSWER", "只有成功回答可保存引用快照")
        if now.tzinfo is None:
            raise ValueError("answer snapshot time must be timezone-aware")
        existing = self._repository.get_by_run(
            system_id=decision.system_id,
            run_id=decision.run_id,
        )
        if existing is not None:
            if existing.answer != answer or existing.degraded_reasons != degraded_reasons:
                raise ConflictError("ANSWER_SNAPSHOT_CONFLICT", "同一问答运行已有不同回答快照")
            return existing
        stored = self._repository.add_or_get(
            AnswerSnapshot(
                id=uuid4(),
                run_id=decision.run_id,
                system_id=decision.system_id,
                answer=answer,
                degraded_reasons=degraded_reasons,
                created_at=now,
            )
        )
        if stored.answer != answer or stored.degraded_reasons != degraded_reasons:
            raise ConflictError("ANSWER_SNAPSHOT_CONFLICT", "同一问答运行已有不同回答快照")
        return stored

    def get_by_run(self, *, system_id: UUID, run_id: UUID) -> AnswerSnapshot | None:
        return self._repository.get_by_run(system_id=system_id, run_id=run_id)
