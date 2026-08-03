from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from knowagent.documents.domain.models import SourceLocator
from knowagent.retrieval.domain.models import EvidenceBundle


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
