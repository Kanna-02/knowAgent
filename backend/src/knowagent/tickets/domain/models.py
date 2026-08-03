from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TicketStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class Ticket:  # pylint: disable=too-many-instance-attributes
    id: UUID
    system_id: UUID
    requester_id: UUID
    source_run_id: UUID
    assignee_id: UUID | None
    status: TicketStatus
    priority: TicketPriority
    title: str
    question: str
    normalized_question: str
    deduplication_key: str
    occurrence_count: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        values = (
            self.title,
            self.question,
            self.normalized_question,
            self.deduplication_key,
        )
        if any(not value.strip() for value in values):
            raise ValueError("ticket text and deduplication key must not be blank")
        if self.occurrence_count <= 0:
            raise ValueError("ticket occurrence count must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("ticket timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TicketOccurrence:
    id: UUID
    ticket_id: UUID
    system_id: UUID
    run_id: UUID
    requester_id: UUID
    question: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("ticket occurrence question must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("ticket occurrence time must be timezone-aware")
