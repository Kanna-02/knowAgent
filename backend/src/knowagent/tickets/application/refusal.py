from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from knowagent.agent.application.evidence_decision import normalize_question
from knowagent.agent.domain.models import EvidenceDecision, EvidenceDecisionOutcome
from knowagent.common.errors import ConflictError, ValidationError
from knowagent.tickets.domain.models import (
    Ticket,
    TicketOccurrence,
    TicketPriority,
    TicketStatus,
)
from knowagent.tickets.ports import TicketRepository

TICKET_TITLE_MAX_LENGTH = 120


class RefusalTicketService:
    def __init__(
        self,
        *,
        repository: TicketRepository,
        deduplication_window: timedelta,
    ) -> None:
        if deduplication_window <= timedelta(0):
            raise ValueError("ticket deduplication window must be positive")
        self._repository = repository
        self._deduplication_window = deduplication_window

    def record_sufficient(self, *, decision: EvidenceDecision) -> None:
        if decision.outcome is not EvidenceDecisionOutcome.SUFFICIENT:
            raise ValidationError(
                "EVIDENCE_DECISION_NOT_SUFFICIENT",
                "拒答判定不能记录为充分证据",
            )
        existing = self._repository.get_decision(run_id=decision.run_id)
        if existing is None:
            self._repository.add_decision(decision=decision, ticket_id=None)
            return
        if existing.outcome is not EvidenceDecisionOutcome.SUFFICIENT:
            raise ConflictError("EVIDENCE_DECISION_CONFLICT", "同一问答运行已有不同判定")
        self._assert_decision_payload_matches(existing, decision)

    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None:
        return self._repository.get_decision(run_id=run_id)

    def create_from_refusal(
        self,
        *,
        decision: EvidenceDecision,
        requester_id: UUID,
        now: datetime,
    ) -> UUID:
        if not decision.outcome.is_refusal:
            raise ValidationError(
                "TICKET_REFUSAL_REQUIRED",
                "只有证据不足或冲突时才能自动创建工单",
            )
        if now.tzinfo is None:
            raise ValueError("ticket creation time must be timezone-aware")

        # Serialize concurrent handling of the same run before any read/write.
        self._repository.acquire_run_lock(run_id=decision.run_id)

        existing_occurrence = self._repository.get_ticket_occurrence(run_id=decision.run_id)
        if existing_occurrence is not None:
            # Replays of the same run must return the same ticket without
            # incrementing the occurrence count. A mismatched requester means
            # the caller is claiming a run that belongs to someone else.
            if existing_occurrence.requester_id != requester_id:
                raise ConflictError(
                    "TICKET_REQUESTER_MISMATCH",
                    "同一问答运行的提问人不一致",
                )
            return existing_occurrence.ticket_id

        existing_decision = self._repository.get_decision(run_id=decision.run_id)
        if existing_decision is not None:
            if existing_decision.ticket_id is None:
                raise ConflictError("EVIDENCE_DECISION_CONFLICT", "同一问答运行已有非拒答判定")
            raise ConflictError("EVIDENCE_DECISION_CONFLICT", "同一问答运行已有判定但无发生记录")

        normalized_question = normalize_question(decision.query)
        deduplication_key = self._deduplication_key(
            system_id=decision.system_id,
            normalized_question=normalized_question,
        )

        # Serialize concurrent handling of the same deduplication key before the
        # rolling-window lookup, so two concurrent requests with the same
        # question cannot both miss the existing ticket and double-insert.
        self._repository.acquire_deduplication_lock(
            system_id=decision.system_id,
            deduplication_key=deduplication_key,
        )

        ticket = self._repository.get_ticket_by_deduplication_key(
            system_id=decision.system_id,
            deduplication_key=deduplication_key,
            updated_after=now - self._deduplication_window,
        )
        if ticket is None:
            ticket = self._repository.add_ticket(
                Ticket(
                    id=uuid4(),
                    system_id=decision.system_id,
                    requester_id=requester_id,
                    source_run_id=decision.run_id,
                    assignee_id=None,
                    status=TicketStatus.OPEN,
                    priority=TicketPriority.NORMAL,
                    title=decision.query.strip()[:TICKET_TITLE_MAX_LENGTH],
                    question=decision.query.strip(),
                    normalized_question=normalized_question,
                    deduplication_key=deduplication_key,
                    occurrence_count=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            ticket = self._repository.increment_ticket_occurrence(ticket_id=ticket.id, now=now)

        self._repository.add_decision(decision=decision, ticket_id=ticket.id)

        # Persist the occurrence after its evidence decision because run_id is
        # protected by a foreign key to evidence_decisions.
        self._repository.add_ticket_occurrence(
            TicketOccurrence(
                id=uuid4(),
                ticket_id=ticket.id,
                system_id=decision.system_id,
                run_id=decision.run_id,
                requester_id=requester_id,
                question=decision.query.strip(),
                created_at=now,
            )
        )
        return ticket.id

    def _deduplication_key(
        self,
        *,
        system_id: UUID,
        normalized_question: str,
    ) -> str:
        # Stable fingerprint over system + question only; the rolling window is
        # enforced at query time via updated_at so two requests a few minutes
        # apart never get different keys merely for straddling a bucket edge.
        material = f"{system_id}:{normalized_question}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _assert_decision_payload_matches(
        existing: EvidenceDecision,
        incoming: EvidenceDecision,
    ) -> None:
        if (
            existing.system_id != incoming.system_id
            or existing.normalized_query != incoming.normalized_query
            or existing.outcome != incoming.outcome
        ):
            raise ConflictError(
                "EVIDENCE_DECISION_CONFLICT",
                "同一问答运行的判定内容不一致",
            )
