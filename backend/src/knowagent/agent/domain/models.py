from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from knowagent.documents.domain.models import SourceLocator
from knowagent.retrieval.domain.models import EvidenceBundle as EvidenceBundle


class GenerationEventKind(StrEnum):
    DELTA = "delta"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    kind: GenerationEventKind
    text: str = ""

    @classmethod
    def delta(cls, text: str) -> Self:
        if not text:
            raise ValueError("generation delta must not be empty")
        return cls(kind=GenerationEventKind.DELTA, text=text)

    @classmethod
    def completed(cls) -> Self:
        return cls(kind=GenerationEventKind.COMPLETED)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    question: str
    evidence: EvidenceBundle


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    scenario: str
    version: str
    content: str
    enabled: bool
    created_at: datetime
    change_note: str

    def __post_init__(self) -> None:
        values = (self.scenario, self.version, self.content, self.change_note)
        if any(not value.strip() for value in values):
            raise ValueError("prompt metadata and content must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("prompt created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CitationSnapshot:  # pylint: disable=too-many-instance-attributes
    rank: int
    claim_rank: int
    chunk_id: UUID
    source_id: UUID
    source_name: str
    source_version: str
    quoted_text: str
    locators: tuple[SourceLocator, ...]


@dataclass(frozen=True, slots=True)
class VerifiedClaim:
    rank: int
    text: str
    citation_ranks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class VerifiedAnswer:
    text: str
    claims: tuple[VerifiedClaim, ...]
    citations: tuple[CitationSnapshot, ...]
    model: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    answer: VerifiedAnswer
    degraded_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnswerSnapshot:
    id: UUID
    run_id: UUID
    system_id: UUID
    answer: VerifiedAnswer
    degraded_reasons: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("answer snapshot time must be timezone-aware")


class EvidenceDecisionOutcome(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"

    @property
    def is_refusal(self) -> bool:
        return self in {self.INSUFFICIENT, self.CONFLICTING}


class EvidenceReasonCode(StrEnum):
    NO_EVIDENCE = "no_evidence"
    SOURCE_LOCATION_MISSING = "source_location_missing"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"
    SCORE_GAP_TOO_SMALL = "score_gap_too_small"
    REQUIRED_TERM_NOT_COVERED = "required_term_not_covered"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    EVIDENCE_BUDGET_EMPTY = "evidence_budget_empty"
    ANSWER_NOT_GROUNDED = "answer_not_grounded"


@dataclass(frozen=True, slots=True)
class EvidenceCandidateSummary:
    chunk_id: UUID
    source_id: UUID
    source_name: str
    source_version: str
    fused_score: float
    channels: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_name.strip() or not self.source_version.strip() or not self.channels:
            raise ValueError("evidence candidate metadata must not be blank")
        if not math.isfinite(self.fused_score):
            raise ValueError("evidence candidate score must be finite")


@dataclass(frozen=True, slots=True)
class EvidenceDecision:  # pylint: disable=too-many-instance-attributes
    id: UUID
    run_id: UUID
    system_id: UUID
    query: str
    normalized_query: str
    outcome: EvidenceDecisionOutcome
    reason_codes: tuple[EvidenceReasonCode, ...]
    score: float | None
    applied_score_threshold: float
    policy_version: str
    candidates: tuple[EvidenceCandidateSummary, ...]
    degraded_reasons: tuple[str, ...]
    decided_at: datetime
    ticket_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.query.strip() or not self.normalized_query.strip():
            raise ValueError("evidence decision query must not be blank")
        if not self.policy_version.strip():
            raise ValueError("evidence policy version must not be blank")
        if not math.isfinite(self.applied_score_threshold):
            raise ValueError("evidence score threshold must be finite")
        if self.applied_score_threshold < 0:
            raise ValueError("evidence score threshold must not be negative")
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("evidence decision score must be finite")
        if self.decided_at.tzinfo is None:
            raise ValueError("evidence decision time must be timezone-aware")
        if self.outcome is EvidenceDecisionOutcome.SUFFICIENT and self.reason_codes:
            raise ValueError("sufficient evidence decision must not include refusal reasons")
        if self.outcome.is_refusal and not self.reason_codes:
            raise ValueError("refusal evidence decision must include at least one reason")


class QuestionResolutionStatus(StrEnum):
    ANSWERED = "answered"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class QuestionResolution:
    status: QuestionResolutionStatus
    decision: EvidenceDecision
    answer: VerifiedAnswer | None
    ticket_id: UUID | None
    reason_codes: tuple[EvidenceReasonCode, ...]
    degraded_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is QuestionResolutionStatus.ANSWERED:
            if self.answer is None or self.ticket_id is not None or self.reason_codes:
                raise ValueError("answered resolution has inconsistent answer or refusal data")
            return
        if self.answer is not None or self.ticket_id is None or not self.reason_codes:
            raise ValueError("refused resolution must include reasons and a ticket")


class QuestionStreamEventKind(StrEnum):
    RETRIEVAL_STARTED = "retrieval_started"
    EVIDENCE_READY = "evidence_ready"
    DECISION = "decision"
    ANSWER_DELTA = "answer_delta"
    ANSWER_COMPLETED = "answer_completed"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class QuestionStreamEvent:
    """Typed event emitted by :meth:`ReliableQuestionService.resolve_stream`.

    The SSE layer translates each event into a ``text/event-stream`` frame.
    ``payload`` is one of ``EvidenceBundle`` (evidence_ready), ``EvidenceDecision``
    (decision/refused), ``str`` (answer_delta) or ``VerifiedAnswer``
    (answer_completed); for ``retrieval_started`` it is ``None``.
    """

    kind: QuestionStreamEventKind
    payload: object
    run_id: UUID
    degraded_reasons: tuple[str, ...] = ()
