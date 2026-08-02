from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowagent.documents.domain.ingestion import (
    DocumentVersionStatus,
    IngestionBundle,
    IngestionStage,
    IngestionStatus,
)


class IngestionJobView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    system_id: UUID
    document_name: str
    filename: str
    media_type: str
    version_status: DocumentVersionStatus
    status: IngestionStatus
    stage: IngestionStage
    progress: int = Field(ge=0, le=100)
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    error_code: str | None
    error_message: str | None
    next_retry_at: datetime | None
    lease_expires_at: datetime | None
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_bundle(cls, bundle: IngestionBundle) -> IngestionJobView:
        return cls(
            job_id=bundle.job.id,
            document_id=bundle.document.id,
            document_version_id=bundle.version.id,
            system_id=bundle.document.system_id,
            document_name=bundle.document.name,
            filename=bundle.version.filename,
            media_type=bundle.version.media_type,
            version_status=bundle.version.status,
            status=bundle.job.status,
            stage=bundle.job.stage,
            progress=bundle.job.progress,
            attempt=bundle.job.attempt,
            max_attempts=bundle.job.max_attempts,
            error_code=bundle.job.error_code,
            error_message=bundle.job.error_message,
            next_retry_at=bundle.job.next_retry_at,
            lease_expires_at=bundle.job.lease_expires_at,
            celery_task_id=bundle.job.celery_task_id,
            created_at=bundle.job.created_at,
            updated_at=bundle.job.updated_at,
        )
