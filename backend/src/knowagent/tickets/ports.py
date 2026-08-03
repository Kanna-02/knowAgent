from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowagent.agent.domain.models import EvidenceDecision
from knowagent.tickets.domain.models import Ticket, TicketOccurrence
from knowagent.tickets.domain.models import (
    KnowledgeCandidate,
    TicketReply,
    TicketStatus,
    TicketTransition,
)


class TicketRepository(Protocol):  # pylint: disable=too-many-public-methods
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

    def lock_ticket(self, *, ticket_id: UUID) -> Ticket | None: ...

    def update_ticket_status(
        self,
        *,
        ticket_id: UUID,
        status: TicketStatus,
        assignee_id: UUID | None,
        now: datetime,
    ) -> None: ...

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

    # ---- workflow: replies, transitions, candidates ----

    def add_reply(self, reply: TicketReply) -> TicketReply: ...

    def list_replies(self, *, ticket_id: UUID) -> tuple[TicketReply, ...]: ...

    def add_transition(self, transition: TicketTransition) -> TicketTransition: ...

    def list_transitions(self, *, ticket_id: UUID) -> tuple[TicketTransition, ...]: ...

    def add_candidate(self, candidate: KnowledgeCandidate) -> KnowledgeCandidate: ...

    def get_candidate(self, *, candidate_id: UUID) -> KnowledgeCandidate | None: ...

    def get_pending_candidate_by_ticket(self, *, ticket_id: UUID) -> KnowledgeCandidate | None: ...

    def approve_candidate(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        knowledge_source_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate: ...

    def reject_candidate(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate: ...

    def create_ticket_knowledge_source(
        self,
        *,
        system_id: UUID,
        ticket_id: UUID,
        now: datetime,
    ) -> UUID: ...

    def create_published_chunk(
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        text: str,
        now: datetime,
    ) -> UUID: ...
