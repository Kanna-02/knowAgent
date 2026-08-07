"""Analytics domain models for Phase 3 quality and operation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class GapSource(StrEnum):
    """Origin of a knowledge-gap finding."""

    REFUSAL = "refusal"
    UNSOLVED_TICKET = "unsolved_ticket"


@dataclass(frozen=True, slots=True)
class AnalyticsWindow:
    """Inclusive time window for analytics queries."""

    started_at: datetime
    ended_at: datetime

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("analytics window timestamps must be timezone-aware")
        if self.started_at > self.ended_at:
            raise ValueError("analytics window started_at must not exceed ended_at")


@dataclass(frozen=True, slots=True)
class SystemOverview:
    """High-level question/ticket counts for one business system.

    Used by the management analytics dashboard to show volume, unresolved
    tickets and refusal counts at a glance.
    """

    system_id: UUID
    question_count: int
    refusal_count: int
    open_ticket_count: int
    resolved_ticket_count: int
    total_ticket_count: int


@dataclass(frozen=True, slots=True)
class FrequentQuestion:
    """A normalized question with its occurrence frequency."""

    normalized_question: str
    occurrence_count: int
    refusal_count: int
    ticket_count: int

    def __post_init__(self) -> None:
        if not self.normalized_question.strip():
            raise ValueError("frequent question text must not be blank")
        if self.occurrence_count <= 0:
            raise ValueError("occurrence count must be positive")
        if self.refusal_count < 0 or self.ticket_count < 0:
            raise ValueError("frequent question sub-counts must not be negative")


@dataclass(frozen=True, slots=True)
class KnowledgeGap:
    """A detected knowledge gap linked to refusals or unsolved tickets."""

    normalized_question: str
    gap_source: GapSource
    occurrence_count: int
    last_seen_at: datetime

    def __post_init__(self) -> None:
        if not self.normalized_question.strip():
            raise ValueError("knowledge gap question must not be blank")
        if self.occurrence_count <= 0:
            raise ValueError("knowledge gap occurrence count must be positive")
        if self.last_seen_at.tzinfo is None:
            raise ValueError("knowledge gap last_seen_at must be timezone-aware")


__all__ = [
    "AnalyticsWindow",
    "FrequentQuestion",
    "GapSource",
    "KnowledgeGap",
    "SystemOverview",
]
