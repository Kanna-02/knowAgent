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


# ---------------------------------------------------------------------------
# Workflow domain — replies, transitions, and knowledge candidates
# ---------------------------------------------------------------------------


class ReplyAuthorRole(StrEnum):
    REQUESTER = "requester"
    ASSIGNEE = "assignee"
    REVIEWER = "reviewer"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


REPLY_MAX_LENGTH = 10_000


def allowed_transitions(current: TicketStatus) -> frozenset[TicketStatus]:
    """Return the set of statuses reachable from ``current`` in one step."""
    table: dict[TicketStatus, frozenset[TicketStatus]] = {
        TicketStatus.OPEN: frozenset({TicketStatus.ASSIGNED, TicketStatus.CLOSED}),
        TicketStatus.ASSIGNED: frozenset(
            {TicketStatus.IN_PROGRESS, TicketStatus.OPEN, TicketStatus.CLOSED}
        ),
        TicketStatus.IN_PROGRESS: frozenset(
            {TicketStatus.RESOLVED, TicketStatus.ASSIGNED, TicketStatus.OPEN}
        ),
        TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.IN_PROGRESS}),
        TicketStatus.CLOSED: frozenset({TicketStatus.OPEN}),
    }
    return table.get(current, frozenset())


@dataclass(frozen=True, slots=True)
class TicketReply:  # pylint: disable=too-many-instance-attributes
    id: UUID
    ticket_id: UUID
    system_id: UUID
    author_id: UUID
    author_role: ReplyAuthorRole
    body: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("ticket reply time must be timezone-aware")
        trimmed = self.body.strip()
        if not trimmed:
            raise ValueError("ticket reply body must not be blank")
        if len(trimmed) > REPLY_MAX_LENGTH:
            raise ValueError("ticket reply body exceeds maximum length")


@dataclass(frozen=True, slots=True)
class TicketTransition:  # pylint: disable=too-many-instance-attributes
    id: UUID
    ticket_id: UUID
    system_id: UUID
    actor_id: UUID
    from_status: TicketStatus | None
    to_status: TicketStatus
    action: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("ticket transition time must be timezone-aware")
        if not self.action.strip():
            raise ValueError("ticket transition action must not be blank")
        if self.from_status is not None and self.from_status is self.to_status:
            raise ValueError("ticket transition must change status")


@dataclass(frozen=True, slots=True)
class KnowledgeCandidate:  # pylint: disable=too-many-instance-attributes
    id: UUID
    ticket_id: UUID
    system_id: UUID
    answer: str
    author_id: UUID
    reviewer_id: UUID | None
    status: CandidateStatus
    knowledge_source_id: UUID | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("knowledge candidate timestamps must be timezone-aware")
        trimmed = self.answer.strip()
        if not trimmed:
            raise ValueError("knowledge candidate answer must not be blank")
        if self.status is CandidateStatus.APPROVED and self.reviewer_id is None:
            raise ValueError("approved candidate must have a reviewer")
        if self.status is CandidateStatus.APPROVED and self.knowledge_source_id is None:
            raise ValueError("approved candidate must reference a knowledge source")


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
