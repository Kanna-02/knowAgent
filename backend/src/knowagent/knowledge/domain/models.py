from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, model_validator

from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.models import KnowledgeChunk as ParsedKnowledgeChunk
from knowagent.documents.domain.models import SourceLocator

__all__ = [
    "KnowledgeChunk",
    "KnowledgeChunkDraft",
    "KnowledgeSource",
    "KnowledgeSourceType",
    "PublicationStatus",
]


class KnowledgeSourceType(StrEnum):
    DOCUMENT = "DOCUMENT"
    TICKET = "TICKET"


class KnowledgeChunkDraft(ParsedKnowledgeChunk):
    model_config = ConfigDict(frozen=True, extra="forbid")

    retrieval_text: str | None = None
    embedding_model: str | None = None
    embedding_model_version: str | None = None

    @model_validator(mode="after")
    def normalize_retrieval_text(self) -> KnowledgeChunkDraft:
        if self.retrieval_text is not None and not self.retrieval_text.strip():
            raise ValueError("retrieval_text must not be blank")
        return self


@dataclass(frozen=True, slots=True)
class KnowledgeSource:  # pylint: disable=too-many-instance-attributes
    id: UUID
    system_id: UUID
    source_type: KnowledgeSourceType
    document_version_id: UUID | None
    ticket_id: UUID | None
    publish_status: PublicationStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:  # pylint: disable=too-many-instance-attributes
    id: UUID
    system_id: UUID
    source_id: UUID
    ordinal: int
    text: str
    token_count: int
    structure_path: tuple[str, ...]
    locators: tuple[SourceLocator, ...]
    retrieval_text: str
    publish_status: PublicationStatus
    created_at: datetime
    updated_at: datetime
    embedding_model: str | None = None
    embedding_model_version: str | None = None
