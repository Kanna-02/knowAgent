from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import (
    EvidenceCandidateSummary,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
)
from knowagent.agent.infrastructure.sqlalchemy_models import EvidenceDecisionRecord
from knowagent.common.errors import NotFoundError
from knowagent.tickets.domain.models import Ticket, TicketOccurrence
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    TicketOccurrenceRecord,
    TicketRecord,
)

# SQLAlchemy exposes SQL functions dynamically; Pylint cannot infer that call contract.
# pylint: disable=not-callable


class SqlAlchemyTicketRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None:
        record = self._session.scalar(
            select(EvidenceDecisionRecord).where(EvidenceDecisionRecord.run_id == run_id)
        )
        return self._to_decision(record) if record is not None else None

    def add_decision(
        self,
        *,
        decision: EvidenceDecision,
        ticket_id: UUID | None,
    ) -> EvidenceDecision:
        record = EvidenceDecisionRecord(
            id=decision.id,
            run_id=decision.run_id,
            system_id=decision.system_id,
            ticket_id=ticket_id,
            query=decision.query,
            normalized_query=decision.normalized_query,
            outcome=decision.outcome,
            reason_codes=[reason.value for reason in decision.reason_codes],
            score=decision.score,
            applied_score_threshold=decision.applied_score_threshold,
            policy_version=decision.policy_version,
            candidate_summaries=[
                {
                    "chunk_id": str(candidate.chunk_id),
                    "source_id": str(candidate.source_id),
                    "source_name": candidate.source_name,
                    "source_version": candidate.source_version,
                    "fused_score": candidate.fused_score,
                    "channels": list(candidate.channels),
                }
                for candidate in decision.candidates
            ],
            degraded_reasons=list(decision.degraded_reasons),
            created_at=decision.decided_at,
            updated_at=decision.decided_at,
        )
        self._session.add(record)
        self._session.flush()
        return replace(decision, ticket_id=ticket_id)

    def acquire_run_lock(self, *, run_id: UUID) -> None:
        self._pg_advisory_xact_lock(self._hash_lock_key(b"run", str(run_id).encode("utf-8")))

    def acquire_deduplication_lock(  # pylint: disable=unused-argument
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
    ) -> None:
        self._pg_advisory_xact_lock(
            self._hash_lock_key(
                b"dedup",
                str(system_id).encode("utf-8"),
                deduplication_key.encode("utf-8"),
            )
        )

    def get_ticket(self, *, ticket_id: UUID) -> Ticket | None:
        record = self._session.get(TicketRecord, ticket_id)
        return self._to_ticket(record) if record is not None else None

    def get_ticket_by_deduplication_key(
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
        updated_after: datetime,
    ) -> Ticket | None:
        record = self._session.scalar(
            select(TicketRecord)
            .where(
                TicketRecord.system_id == system_id,
                TicketRecord.deduplication_key == deduplication_key,
                TicketRecord.updated_at >= updated_after,
            )
            .with_for_update()
        )
        return self._to_ticket(record) if record is not None else None

    def add_ticket(self, ticket: Ticket) -> Ticket:
        self._session.add(
            TicketRecord(
                id=ticket.id,
                system_id=ticket.system_id,
                requester_id=ticket.requester_id,
                source_run_id=ticket.source_run_id,
                assignee_id=ticket.assignee_id,
                status=ticket.status,
                priority=ticket.priority,
                title=ticket.title,
                question=ticket.question,
                normalized_question=ticket.normalized_question,
                deduplication_key=ticket.deduplication_key,
                occurrence_count=ticket.occurrence_count,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
            )
        )
        self._session.flush()
        return ticket

    def increment_ticket_occurrence(self, *, ticket_id: UUID, now: datetime) -> Ticket:
        record = self._session.scalar(
            select(TicketRecord).where(TicketRecord.id == ticket_id).with_for_update()
        )
        if record is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        record.occurrence_count += 1
        record.updated_at = now
        self._session.flush()
        return self._to_ticket(record)

    def get_ticket_occurrence(self, *, run_id: UUID) -> TicketOccurrence | None:
        record = self._session.scalar(
            select(TicketOccurrenceRecord).where(TicketOccurrenceRecord.run_id == run_id)
        )
        return self._to_occurrence(record) if record is not None else None

    def add_ticket_occurrence(self, occurrence: TicketOccurrence) -> TicketOccurrence:
        self._session.add(
            TicketOccurrenceRecord(
                id=occurrence.id,
                ticket_id=occurrence.ticket_id,
                system_id=occurrence.system_id,
                run_id=occurrence.run_id,
                requester_id=occurrence.requester_id,
                question=occurrence.question,
                created_at=occurrence.created_at,
            )
        )
        self._session.flush()
        return occurrence

    def list_ticket_occurrences(self, *, ticket_id: UUID) -> tuple[TicketOccurrence, ...]:
        records = self._session.scalars(
            select(TicketOccurrenceRecord)
            .where(TicketOccurrenceRecord.ticket_id == ticket_id)
            .order_by(TicketOccurrenceRecord.created_at)
        )
        return tuple(self._to_occurrence(record) for record in records)

    def count_tickets(self) -> int:
        return int(self._session.scalar(select(func.count(TicketRecord.id))) or 0)

    def _pg_advisory_xact_lock(self, lock_id: int) -> None:
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            self._session.execute(select(func.pg_advisory_xact_lock(lock_id)))
        # Non-PostgreSQL dialects (e.g. the in-memory SQLite used in unit tests)
        # have no advisory locks; transactional isolation plus the unique
        # constraints on source_run_id/run_id already serialize concurrent work.

    @staticmethod
    def _hash_lock_key(*parts: bytes) -> int:
        digest = hashlib.sha256(b"|".join(parts)).digest()
        return int.from_bytes(digest[:8], "big", signed=True)

    @staticmethod
    def _to_decision(record: EvidenceDecisionRecord) -> EvidenceDecision:
        candidates = tuple(
            EvidenceCandidateSummary(
                chunk_id=UUID(str(candidate["chunk_id"])),
                source_id=UUID(str(candidate["source_id"])),
                source_name=str(candidate["source_name"]),
                source_version=str(candidate["source_version"]),
                fused_score=float(cast(str | int | float, candidate["fused_score"])),
                channels=tuple(
                    str(channel) for channel in cast(list[object], candidate["channels"])
                ),
            )
            for candidate in record.candidate_summaries
        )
        return EvidenceDecision(
            id=record.id,
            run_id=record.run_id,
            system_id=record.system_id,
            query=record.query,
            normalized_query=record.normalized_query,
            outcome=EvidenceDecisionOutcome(record.outcome),
            reason_codes=tuple(EvidenceReasonCode(code) for code in record.reason_codes),
            score=record.score,
            applied_score_threshold=record.applied_score_threshold,
            policy_version=record.policy_version,
            candidates=candidates,
            degraded_reasons=tuple(record.degraded_reasons),
            decided_at=_as_utc(record.created_at),
            ticket_id=record.ticket_id,
        )

    @staticmethod
    def _to_ticket(record: TicketRecord) -> Ticket:
        return Ticket(
            id=record.id,
            system_id=record.system_id,
            requester_id=record.requester_id,
            source_run_id=record.source_run_id,
            assignee_id=record.assignee_id,
            status=record.status,
            priority=record.priority,
            title=record.title,
            question=record.question,
            normalized_question=record.normalized_question,
            deduplication_key=record.deduplication_key,
            occurrence_count=record.occurrence_count,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )

    @staticmethod
    def _to_occurrence(record: TicketOccurrenceRecord) -> TicketOccurrence:
        return TicketOccurrence(
            id=record.id,
            ticket_id=record.ticket_id,
            system_id=record.system_id,
            run_id=record.run_id,
            requester_id=record.requester_id,
            question=record.question,
            created_at=_as_utc(record.created_at),
        )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
