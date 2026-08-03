from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, model_validator

from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.models import KnowledgeChunk as ParsedKnowledgeChunk
from knowagent.documents.domain.models import SourceLocator

__all__ = [
    "ChunkEmbeddingUpdate",
    "KnowledgeChunk",
    "KnowledgeChunkDraft",
    "KnowledgeIndexSummary",
    "KnowledgeSource",
    "KnowledgeSourceType",
    "PublicationStatus",
]


class KnowledgeSourceType(StrEnum):
    DOCUMENT = "DOCUMENT"
    TICKET = "TICKET"


@dataclass(frozen=True, slots=True)
class ChunkEmbeddingUpdate:
    chunk_id: UUID
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeIndexSummary:
    source_id: UUID
    chunk_count: int
    model: str
    model_version: str
    dimension: int


class KnowledgeChunkDraft(ParsedKnowledgeChunk):
    model_config = ConfigDict(frozen=True, extra="forbid")

    retrieval_text: str | None = None
    embedding_model: str | None = None
    embedding_model_version: str | None = None
    embedding: tuple[float, ...] | None = None

    @model_validator(mode="after")
    def normalize_retrieval_text(self) -> KnowledgeChunkDraft:
        if self.retrieval_text is not None and not self.retrieval_text.strip():
            raise ValueError("retrieval_text must not be blank")
        if self.embedding is not None:
            if not self.embedding:
                raise ValueError("embedding must not be empty")
            if not all(math.isfinite(value) for value in self.embedding):
                raise ValueError("embedding values must be finite")
            if not self.embedding_model or not self.embedding_model_version:
                raise ValueError("embedding model metadata is required with an embedding")
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
    embedding: tuple[float, ...] | None = None
