from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import BinaryIO, Protocol
from uuid import UUID

from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersionStatus,
    IngestionBundle,
    IngestionJob,
    IngestionStage,
)
from knowagent.documents.domain.models import ParsedDocument, SourceType


class DocumentParser(Protocol):
    @property
    def source_type(self) -> SourceType: ...

    def supports(self, *, media_type: str, filename: str) -> bool: ...

    def parse(
        self,
        *,
        content: bytes,
        document_id: UUID,
        document_version_id: UUID,
    ) -> ParsedDocument: ...


class ObjectStore(Protocol):
    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str,
        content_length: int,
    ) -> None: ...

    def get(self, *, key: str) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


class IngestionRepository(Protocol):
    def get_document(self, *, system_id: UUID, document_id: UUID) -> Document | None: ...

    def next_version_no(self, *, system_id: UUID, document_id: UUID) -> int: ...

    def get_by_idempotency_key(
        self, key: str, *, actor_id: UUID, system_id: UUID
    ) -> IngestionBundle | None: ...

    def add(self, bundle: IngestionBundle) -> IngestionBundle: ...

    def get_job(self, job_id: UUID) -> IngestionJob | None: ...

    def save_job(self, job: IngestionJob) -> IngestionJob: ...

    def dispatchable_job_ids(
        self, *, now: datetime, stale_before: datetime, limit: int
    ) -> list[UUID]: ...


class IngestionCoordinator(Protocol):
    def get_job(self, job_id: UUID) -> IngestionJob | None: ...

    def claim(
        self, job_id: UUID, *, owner: str, now: datetime, lease_seconds: int
    ) -> IngestionBundle | None: ...

    def advance(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        stage: IngestionStage,
        progress: int,
        version_status: DocumentVersionStatus,
        now: datetime,
    ) -> IngestionBundle: ...

    def claim_continuation(
        self, job_id: UUID, *, owner: str, now: datetime, lease_seconds: int
    ) -> IngestionBundle | None: ...

    def release_for_continuation(
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        now: datetime,
    ) -> IngestionBundle: ...

    def record_chunk_manifest(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        manifest_key: str,
        chunk_count: int,
        parser_name: str,
        parser_version: str,
        schema_version: str,
        now: datetime,
    ) -> IngestionBundle: ...

    def complete(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        manifest_key: str,
        chunk_count: int,
        parser_name: str,
        parser_version: str,
        schema_version: str,
        now: datetime,
        version_status: DocumentVersionStatus = DocumentVersionStatus.CHUNKED,
    ) -> IngestionBundle: ...

    def fail(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        error_code: str,
        error_message: str,
        retryable: bool,
        version_status: DocumentVersionStatus,
        now: datetime,
        retry_base_seconds: int,
    ) -> IngestionBundle: ...

    def recover_and_find_dispatchable(
        self, *, now: datetime, stale_before: datetime, limit: int
    ) -> list[UUID]: ...

    def mark_dispatched(self, job_id: UUID, *, celery_task_id: str, now: datetime) -> None: ...


class IngestionDispatcher(Protocol):  # pylint: disable=too-few-public-methods
    def enqueue(self, job_id: UUID) -> str: ...


class ChunkIngestionHook(Protocol):  # pylint: disable=too-few-public-methods
    """Persist parsed chunks as draft knowledge and advance the version to READY_DRAFT.

    Invoked by :class:`IngestionProcessor` after the chunk manifest is written.
    Implementations also trigger embedding indexing. Transient provider
    failures propagate into the persistent ingestion retry state machine.
    """

    def ingest_chunks(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        manifest_key: str,
        now: datetime,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[UUID, int]: ...

    def prepare_chunks(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        manifest_key: str,
        now: datetime,
    ) -> tuple[UUID, int]: ...

    def source_id_for_version(self, *, system_id: UUID, document_version_id: UUID) -> UUID: ...

    def index_next_batch(self, *, system_id: UUID, source_id: UUID, now: datetime) -> object: ...
