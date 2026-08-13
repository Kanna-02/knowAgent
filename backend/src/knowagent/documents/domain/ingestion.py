from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from knowagent.common.lifecycle import PublicationStatus


class DocumentVersionStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    CHUNKED = "CHUNKED"
    READY_DRAFT = "READY_DRAFT"
    OCR_REQUIRED = "OCR_REQUIRED"
    FAILED = "FAILED"


class IngestionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IngestionStage(StrEnum):
    STORED = "STORED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    COMPLETED = "COMPLETED"


_STAGE_ORDER = {
    IngestionStage.STORED: 0,
    IngestionStage.PARSING: 1,
    IngestionStage.CHUNKING: 2,
    IngestionStage.COMPLETED: 3,
}


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    system_id: UUID
    name: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    current_published_version_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DocumentVersion:  # pylint: disable=too-many-instance-attributes
    id: UUID
    document_id: UUID
    system_id: UUID
    version_no: int
    object_key: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    status: DocumentVersionStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    chunk_manifest_key: str | None = None
    chunk_count: int = 0
    parser_name: str | None = None
    parser_version: str | None = None
    schema_version: str | None = None
    publish_status: PublicationStatus = PublicationStatus.DRAFT
    published_at: datetime | None = None
    retired_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IngestionJob:  # pylint: disable=too-many-instance-attributes
    id: UUID
    document_version_id: UUID
    actor_id: UUID
    system_id: UUID
    idempotency_key: str
    status: IngestionStatus
    stage: IngestionStage
    progress: int
    attempt: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    requested_document_id: UUID | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    next_retry_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    celery_task_id: str | None = None
    last_dispatched_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def new(  # pylint: disable=too-many-arguments
        cls,
        *,
        document_version_id: UUID,
        actor_id: UUID,
        system_id: UUID,
        requested_document_id: UUID | None = None,
        idempotency_key: str,
        max_attempts: int,
        now: datetime,
    ) -> IngestionJob:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        return cls(
            id=uuid4(),
            document_version_id=document_version_id,
            actor_id=actor_id,
            system_id=system_id,
            requested_document_id=requested_document_id,
            idempotency_key=idempotency_key,
            status=IngestionStatus.QUEUED,
            stage=IngestionStage.STORED,
            progress=0,
            attempt=0,
            max_attempts=max_attempts,
            created_at=now,
            updated_at=now,
        )

    def claim(self, *, owner: str, now: datetime, lease_seconds: int) -> IngestionJob:
        due_retry = (
            self.status is IngestionStatus.RETRY_SCHEDULED
            and self.next_retry_at is not None
            and self.next_retry_at <= now
        )
        if self.status is not IngestionStatus.QUEUED and not due_retry:
            raise ValueError("job cannot be claimed from its current status")
        if not owner.strip() or lease_seconds <= 0:
            raise ValueError("claim requires an owner and positive lease")
        restarting = (
            self.status is IngestionStatus.RETRY_SCHEDULED and self.stage is IngestionStage.STORED
        )
        return replace(
            self,
            status=IngestionStatus.RUNNING,
            stage=IngestionStage.STORED if restarting else self.stage,
            progress=0 if restarting else self.progress,
            attempt=self.attempt + 1,
            lease_owner=owner,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            next_retry_at=None,
            error_code=None,
            error_message=None,
            started_at=self.started_at or now,
            updated_at=now,
        )

    def release_for_continuation(self, *, now: datetime) -> IngestionJob:
        """Release a batch lease without consuming the document retry budget."""
        if self.status is not IngestionStatus.RUNNING:
            raise ValueError("only a running job can continue")
        return replace(
            self,
            status=IngestionStatus.QUEUED,
            lease_owner=None,
            lease_expires_at=None,
            next_retry_at=None,
            celery_task_id=None,
            last_dispatched_at=None,
            updated_at=now,
        )

    def claim_continuation(self, *, owner: str, now: datetime, lease_seconds: int) -> IngestionJob:
        due_retry = (
            self.status is IngestionStatus.RETRY_SCHEDULED
            and self.next_retry_at is not None
            and self.next_retry_at <= now
        )
        if self.status is not IngestionStatus.QUEUED and not due_retry:
            raise ValueError("job cannot be continued from its current status")
        if self.stage is not IngestionStage.CHUNKING:
            raise ValueError("only a chunking job can continue")
        if not owner.strip() or lease_seconds <= 0:
            raise ValueError("claim requires an owner and positive lease")
        return replace(
            self,
            status=IngestionStatus.RUNNING,
            attempt=self.attempt + (1 if due_retry else 0),
            lease_owner=owner,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            next_retry_at=None,
            error_code=None,
            error_message=None,
            celery_task_id=None,
            last_dispatched_at=None,
            started_at=self.started_at or now,
            updated_at=now,
        )

    def advance(self, stage: IngestionStage, *, progress: int, now: datetime) -> IngestionJob:
        if self.status is not IngestionStatus.RUNNING:
            raise ValueError("only a running job can advance")
        if not self.progress <= progress <= 99:
            raise ValueError("progress must be monotonic and below completion")
        if _STAGE_ORDER[stage] < _STAGE_ORDER[self.stage]:
            raise ValueError("stage and progress cannot regress")
        return replace(self, stage=stage, progress=progress, updated_at=now)

    def complete(self, *, now: datetime) -> IngestionJob:
        if self.status is not IngestionStatus.RUNNING:
            raise ValueError("only a running job can complete")
        return replace(
            self,
            status=IngestionStatus.SUCCEEDED,
            stage=IngestionStage.COMPLETED,
            progress=100,
            lease_owner=None,
            lease_expires_at=None,
            next_retry_at=None,
            error_code=None,
            error_message=None,
            completed_at=now,
            updated_at=now,
        )

    def fail(
        self,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
        now: datetime,
        retry_base_seconds: int,
    ) -> IngestionJob:
        if self.status is not IngestionStatus.RUNNING:
            raise ValueError("only a running job can fail")
        can_retry = retryable and self.attempt < self.max_attempts
        delay = retry_base_seconds * (2 ** max(self.attempt - 1, 0))
        return replace(
            self,
            status=(IngestionStatus.RETRY_SCHEDULED if can_retry else IngestionStatus.FAILED),
            lease_owner=None,
            lease_expires_at=None,
            next_retry_at=now + timedelta(seconds=delay) if can_retry else None,
            error_code=error_code,
            error_message=error_message,
            celery_task_id=None if can_retry else self.celery_task_id,
            last_dispatched_at=None if can_retry else self.last_dispatched_at,
            completed_at=None if can_retry else now,
            updated_at=now,
        )

    def recover_expired(self, *, now: datetime) -> IngestionJob:
        if (
            self.status is not IngestionStatus.RUNNING
            or self.lease_expires_at is None
            or self.lease_expires_at > now
        ):
            raise ValueError("job does not have an expired lease")
        exhausted = self.attempt >= self.max_attempts
        return replace(
            self,
            status=IngestionStatus.FAILED if exhausted else IngestionStatus.QUEUED,
            stage=(
                IngestionStage.STORED
                if not exhausted and self.stage is not IngestionStage.CHUNKING
                else self.stage
            ),
            progress=(
                0 if not exhausted and self.stage is not IngestionStage.CHUNKING else self.progress
            ),
            lease_owner=None,
            lease_expires_at=None,
            next_retry_at=None,
            error_code="LEASE_EXPIRED",
            error_message="处理进程中断，任务租约已过期",
            celery_task_id=self.celery_task_id if exhausted else None,
            last_dispatched_at=self.last_dispatched_at if exhausted else None,
            completed_at=now if exhausted else None,
            updated_at=now,
        )

    def manual_retry(self, *, now: datetime) -> IngestionJob:
        if self.status is not IngestionStatus.FAILED:
            raise ValueError("only a failed job can be retried manually")
        return replace(
            self,
            status=IngestionStatus.QUEUED,
            stage=IngestionStage.STORED,
            progress=0,
            attempt=0,
            lease_owner=None,
            lease_expires_at=None,
            next_retry_at=None,
            error_code=None,
            error_message=None,
            completed_at=None,
            last_dispatched_at=None,
            celery_task_id=None,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class IngestionBundle:
    document: Document
    version: DocumentVersion
    job: IngestionJob
