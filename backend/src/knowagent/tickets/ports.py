from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowagent.agent.domain.models import EvidenceDecision
from knowagent.tickets.domain.models import Ticket, TicketOccurrence


class TicketRepository(Protocol):
    def acquire_run_lock(self, *, run_id: UUID) -> None: ...

    def acquire_deduplication_lock(
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
    ) -> None: ...

    def get_decision(self, *, run_id: UUID) -> EvidenceDecision | None: ...

    def add_decision(
        self,
        *,
        decision: EvidenceDecision,
        ticket_id: UUID | None,
    ) -> EvidenceDecision: ...

    def get_ticket(self, *, ticket_id: UUID) -> Ticket | None: ...

    def get_ticket_by_deduplication_key(
        self,
        *,
        system_id: UUID,
        deduplication_key: str,
        updated_after: datetime,
    ) -> Ticket | None: ...

    def add_ticket(self, ticket: Ticket) -> Ticket: ...

    def increment_ticket_occurrence(self, *, ticket_id: UUID, now: datetime) -> Ticket: ...

    def get_ticket_occurrence(self, *, run_id: UUID) -> TicketOccurrence | None: ...

    def add_ticket_occurrence(self, occurrence: TicketOccurrence) -> TicketOccurrence: ...
