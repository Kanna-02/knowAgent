from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.ingestion import DocumentVersionStatus


class DocumentVersionView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    document_id: UUID
    system_id: UUID
    version_no: int = Field(ge=1)
    filename: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    status: DocumentVersionStatus
    publish_status: PublicationStatus
    chunk_count: int = Field(ge=0)
    parser_name: str | None = None
    parser_version: str | None = None
    published_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentVersionPage(BaseModel):
    items: list[DocumentVersionView]
    page: int
    page_size: int
    total: int


class DocumentView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    system_id: UUID
    name: str
    current_published_version_id: UUID | None = None
    current_published_version_no: int | None = None
    latest_version_no: int | None = None
    latest_version_status: DocumentVersionStatus | None = None
    version_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentView]
    page: int
    page_size: int
    total: int


class PublishVersionResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    document_id: UUID
    version_id: UUID
    system_id: UUID
    publish_status: PublicationStatus
    published_at: datetime


class RetireVersionResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    document_id: UUID
    version_id: UUID
    system_id: UUID
    publish_status: PublicationStatus
    retired_at: datetime
