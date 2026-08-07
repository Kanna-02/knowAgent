"""Application service for conversation, FAQ and knowledge-gap analytics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import EvidenceDecisionOutcome
from knowagent.agent.infrastructure.sqlalchemy_models import (
    ConversationMessageRecord,
    EvidenceDecisionRecord,
)
from knowagent.analytics.domain.models import (
    AnalyticsWindow,
    FrequentQuestion,
    GapSource,
    KnowledgeGap,
    SystemOverview,
)
from knowagent.tickets.domain.models import TicketStatus
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    TicketOccurrenceRecord,
    TicketRecord,
)

# SQLAlchemy dynamic namespaces trigger false positives on record columns.
# pylint: disable=not-callable

MAX_TOP_ITEMS = 100
DEFAULT_TOP_ITEMS = 20

_OPEN_STATUSES = frozenset({TicketStatus.OPEN, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS})
_RESOLVED_STATUSES = frozenset({TicketStatus.RESOLVED, TicketStatus.CLOSED})


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_limit(limit: int, *, name: str = "limit") -> None:
    if limit <= 0:
        raise ValueError(f"{name} must be positive")
    if limit > MAX_TOP_ITEMS:
        raise ValueError(f"{name} must not exceed {MAX_TOP_ITEMS}")


class AnalyticsService:
    """Read-side analytics built on conversation messages and ticket data.

    All methods are scoped by ``system_id``. The service performs only
    read queries and never mutates state.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_system_overview(
        self,
        *,
        system_id: UUID,
        window: AnalyticsWindow,
    ) -> SystemOverview:
        started = _aware(window.started_at)
        ended = _aware(window.ended_at)
        question_count = self._count_user_questions(system_id, started, ended)
        refusal_count = self._count_refusals(system_id, started, ended)
        open_count, resolved_count, total_count = self._count_tickets(system_id, started, ended)
        return SystemOverview(
            system_id=system_id,
            question_count=question_count,
            refusal_count=refusal_count,
            open_ticket_count=open_count,
            resolved_ticket_count=resolved_count,
            total_ticket_count=total_count,
        )

    def list_frequent_questions(
        self,
        *,
        system_id: UUID,
        window: AnalyticsWindow,
        top_n: int = DEFAULT_TOP_ITEMS,
    ) -> list[FrequentQuestion]:
        _validate_limit(top_n, name="top_n")
        started = _aware(window.started_at)
        ended = _aware(window.ended_at)
        rows = self._session.execute(
            select(
                TicketRecord.normalized_question.label("norm_q"),
                func.sum(TicketRecord.occurrence_count).label("occ"),
            )
            .where(
                TicketRecord.system_id == system_id,
                TicketRecord.created_at >= started,
                TicketRecord.created_at <= ended,
            )
            .group_by("norm_q")
            .order_by(func.sum(TicketRecord.occurrence_count).desc(), "norm_q")
            .limit(top_n)
        ).all()
        return [
            FrequentQuestion(
                normalized_question=row.norm_q,
                occurrence_count=int(row.occ),
                refusal_count=self._refusal_count_for(system_id, row.norm_q, started, ended),
                ticket_count=self._ticket_count_for(system_id, row.norm_q, started, ended),
            )
            for row in rows
        ]

    def list_knowledge_gaps(
        self,
        *,
        system_id: UUID,
        window: AnalyticsWindow,
        top_n: int = DEFAULT_TOP_ITEMS,
    ) -> list[KnowledgeGap]:
        _validate_limit(top_n, name="top_n")
        started = _aware(window.started_at)
        ended = _aware(window.ended_at)
        refusals = self._refusal_gaps(system_id, started, ended, top_n)
        unsolved = self._unsolved_ticket_gaps(system_id, started, ended, top_n)
        merged = self._merge_gaps(refusals, unsolved)
        return merged[:top_n]

    # --- private helpers --------------------------------------------------

    def _count_user_questions(self, system_id: UUID, started: datetime, ended: datetime) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(ConversationMessageRecord)
                .where(
                    ConversationMessageRecord.system_id == system_id,
                    ConversationMessageRecord.role == "user",
                    ConversationMessageRecord.created_at >= started,
                    ConversationMessageRecord.created_at <= ended,
                )
            )
            or 0
        )

    def _count_refusals(self, system_id: UUID, started: datetime, ended: datetime) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(EvidenceDecisionRecord)
                .where(
                    EvidenceDecisionRecord.system_id == system_id,
                    EvidenceDecisionRecord.outcome == EvidenceDecisionOutcome.INSUFFICIENT,
                    EvidenceDecisionRecord.created_at >= started,
                    EvidenceDecisionRecord.created_at <= ended,
                )
            )
            or 0
        )

    def _count_tickets(
        self, system_id: UUID, started: datetime, ended: datetime
    ) -> tuple[int, int, int]:
        total_rows = self._session.scalars(
            select(TicketRecord).where(
                TicketRecord.system_id == system_id,
                TicketRecord.created_at >= started,
                TicketRecord.created_at <= ended,
            )
        ).all()
        open_count = sum(1 for row in total_rows if row.status in _OPEN_STATUSES)
        resolved_count = sum(1 for row in total_rows if row.status in _RESOLVED_STATUSES)
        return open_count, resolved_count, len(total_rows)

    def _refusal_count_for(
        self,
        system_id: UUID,
        normalized_question: str,
        started: datetime,
        ended: datetime,
    ) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(EvidenceDecisionRecord)
                .where(
                    EvidenceDecisionRecord.system_id == system_id,
                    EvidenceDecisionRecord.normalized_query == normalized_question,
                    EvidenceDecisionRecord.outcome == EvidenceDecisionOutcome.INSUFFICIENT,
                    EvidenceDecisionRecord.created_at >= started,
                    EvidenceDecisionRecord.created_at <= ended,
                )
            )
            or 0
        )

    def _ticket_count_for(
        self,
        system_id: UUID,
        normalized_question: str,
        started: datetime,
        ended: datetime,
    ) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(TicketRecord)
                .where(
                    TicketRecord.system_id == system_id,
                    TicketRecord.normalized_question == normalized_question,
                    TicketRecord.created_at >= started,
                    TicketRecord.created_at <= ended,
                )
            )
            or 0
        )

    def _refusal_gaps(
        self,
        system_id: UUID,
        started: datetime,
        ended: datetime,
        top_n: int,
    ) -> list[KnowledgeGap]:
        rows = self._session.execute(
            select(
                EvidenceDecisionRecord.normalized_query.label("norm_q"),
                func.count(EvidenceDecisionRecord.id).label("occ"),
                func.max(EvidenceDecisionRecord.created_at).label("last_seen"),
            )
            .where(
                EvidenceDecisionRecord.system_id == system_id,
                EvidenceDecisionRecord.outcome == EvidenceDecisionOutcome.INSUFFICIENT,
                EvidenceDecisionRecord.created_at >= started,
                EvidenceDecisionRecord.created_at <= ended,
            )
            .group_by("norm_q")
            .order_by(func.count(EvidenceDecisionRecord.id).desc(), "norm_q")
            .limit(top_n)
        ).all()
        return [
            KnowledgeGap(
                normalized_question=row.norm_q,
                gap_source=GapSource.REFUSAL,
                occurrence_count=int(row.occ),
                last_seen_at=_aware(row.last_seen),
            )
            for row in rows
        ]

    def _unsolved_ticket_gaps(
        self,
        system_id: UUID,
        started: datetime,
        ended: datetime,
        top_n: int,
    ) -> list[KnowledgeGap]:
        open_statuses_list = [status.value for status in _OPEN_STATUSES]
        rows = self._session.execute(
            select(
                TicketRecord.normalized_question.label("norm_q"),
                func.count(TicketOccurrenceRecord.id).label("occ"),
                func.max(TicketOccurrenceRecord.created_at).label("last_seen"),
            )
            .join(
                TicketRecord,
                (TicketRecord.id == TicketOccurrenceRecord.ticket_id)
                & (TicketRecord.system_id == TicketOccurrenceRecord.system_id),
            )
            .where(
                TicketOccurrenceRecord.system_id == system_id,
                TicketOccurrenceRecord.created_at >= started,
                TicketOccurrenceRecord.created_at <= ended,
                TicketRecord.status.in_(open_statuses_list),
            )
            .group_by("norm_q")
            .order_by(func.count(TicketOccurrenceRecord.id).desc(), "norm_q")
            .limit(top_n)
        ).all()
        return [
            KnowledgeGap(
                normalized_question=row.norm_q,
                gap_source=GapSource.UNSOLVED_TICKET,
                occurrence_count=int(row.occ),
                last_seen_at=_aware(row.last_seen),
            )
            for row in rows
        ]

    @staticmethod
    def _merge_gaps(
        refusals: list[KnowledgeGap], unsolved: list[KnowledgeGap]
    ) -> list[KnowledgeGap]:
        """Merge and sort by occurrence count, keeping the higher-rank source."""

        by_question: dict[str, KnowledgeGap] = {}
        for gap in refusals + unsolved:
            existing = by_question.get(gap.normalized_question)
            if existing is None or gap.occurrence_count > existing.occurrence_count:
                by_question[gap.normalized_question] = gap
        return sorted(
            by_question.values(),
            key=lambda g: (g.occurrence_count, g.last_seen_at),
            reverse=True,
        )
