from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

from knowagent.documents.application.chunking import StructureAwareChunker
from knowagent.documents.application.processor import IngestionProcessor, IngestionRecoveryService
from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionBundle,
    IngestionJob,
    IngestionStage,
    IngestionStatus,
)
from knowagent.documents.domain.models import SourceType
from knowagent.documents.errors import DocumentParseError, ParseErrorCode
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.platform.object_store import ObjectStoreError

NOW = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)


def make_bundle() -> IngestionBundle:
    document_id, version_id, actor_id, system_id = uuid4(), uuid4(), uuid4(), uuid4()
    return IngestionBundle(
        document=Document(
            id=document_id,
            system_id=system_id,
            name="Guide",
            created_by=actor_id,
            created_at=NOW,
            updated_at=NOW,
        ),
        version=DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_no=1,
            object_key="documents/source.md",
            filename="guide.md",
            media_type="text/markdown",
            size_bytes=25,
            sha256="a" * 64,
            status=DocumentVersionStatus.UPLOADED,
            created_by=actor_id,
            created_at=NOW,
            updated_at=NOW,
        ),
        job=IngestionJob.new(
            document_version_id=version_id,
            actor_id=actor_id,
            system_id=system_id,
            idempotency_key="upload-001",
            max_attempts=3,
            now=NOW,
        ),
    )


class CoordinatorFake:
    def __init__(self, bundle: IngestionBundle) -> None:
        self.bundle = bundle
        self.dispatchable: list[UUID] = []
        self.dispatched: list[tuple[UUID, str]] = []

    def claim(
        self, job_id: UUID, *, owner: str, now: datetime, lease_seconds: int
    ) -> IngestionBundle | None:
        if self.bundle.job.id != job_id or self.bundle.job.status is IngestionStatus.SUCCEEDED:
            return None
        self.bundle = replace(
            self.bundle,
            job=self.bundle.job.claim(owner=owner, now=now, lease_seconds=lease_seconds),
        )
        return self.bundle

    def advance(
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        stage: IngestionStage,
        progress: int,
        version_status: DocumentVersionStatus,
        now: datetime,
    ) -> IngestionBundle:
        assert owner and attempt == self.bundle.job.attempt
        assert job_id == self.bundle.job.id
        self.bundle = replace(
            self.bundle,
            job=self.bundle.job.advance(stage, progress=progress, now=now),
            version=replace(self.bundle.version, status=version_status, updated_at=now),
        )
        return self.bundle

    def complete(
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
    ) -> IngestionBundle:
        assert owner and attempt == self.bundle.job.attempt
        assert job_id == self.bundle.job.id
        self.bundle = replace(
            self.bundle,
            job=self.bundle.job.complete(now=now),
            version=replace(
                self.bundle.version,
                status=DocumentVersionStatus.CHUNKED,
                chunk_manifest_key=manifest_key,
                chunk_count=chunk_count,
                parser_name=parser_name,
                parser_version=parser_version,
                schema_version=schema_version,
                updated_at=now,
            ),
        )
        return self.bundle

    def fail(
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
    ) -> IngestionBundle:
        assert owner and attempt == self.bundle.job.attempt
        assert job_id == self.bundle.job.id
        failed = self.bundle.job.fail(
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            now=now,
            retry_base_seconds=retry_base_seconds,
        )
        effective_status = (
            DocumentVersionStatus.UPLOADED
            if failed.status is IngestionStatus.RETRY_SCHEDULED
            else version_status
        )
        self.bundle = replace(
            self.bundle,
            job=failed,
            version=replace(self.bundle.version, status=effective_status, updated_at=now),
        )
        return self.bundle

    def recover_and_find_dispatchable(
        self, *, now: datetime, stale_before: datetime, limit: int
    ) -> list[UUID]:
        del now, stale_before
        return self.dispatchable[:limit]

    def mark_dispatched(self, job_id: UUID, *, celery_task_id: str, now: datetime) -> None:
        del now
        self.dispatched.append((job_id, celery_task_id))


class ObjectStoreFake:
    def __init__(self) -> None:
        self.objects = {"documents/source.md": b"# Guide\n\nStable content\n"}
        self.get_error: ObjectStoreError | None = None

    def put(
        self,
        *,
        key: str,
        content: BytesIO,
        content_type: str,
        content_length: int,
    ) -> None:
        del content_type, content_length
        self.objects[key] = content.read()

    def get(self, *, key: str) -> bytes:
        if self.get_error:
            raise self.get_error
        return self.objects[key]

    def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


class FailingParser:
    @property
    def source_type(self) -> SourceType:
        return SourceType.MARKDOWN

    def supports(self, *, media_type: str, filename: str) -> bool:
        del media_type, filename
        return True

    def parse(self, **_: object) -> None:
        raise DocumentParseError(ParseErrorCode.OCR_REQUIRED, "需要 OCR")


class DispatcherFake:
    def __init__(self) -> None:
        self.jobs: list[UUID] = []

    def enqueue(self, job_id: UUID) -> str:
        self.jobs.append(job_id)
        return f"task-{job_id}"


def test_processor_persists_manifest_progress_and_terminal_metadata() -> None:
    coordinator = CoordinatorFake(make_bundle())
    store = ObjectStoreFake()
    processor = IngestionProcessor(
        coordinator=coordinator,
        object_store=store,
        parser_registry=ParserRegistry.default(),
        chunker=StructureAwareChunker(),
        lease_seconds=600,
        retry_base_seconds=10,
        clock=lambda: NOW,
    )

    completed = processor.process(coordinator.bundle.job.id, worker_id="worker-1")

    assert completed is not None
    assert completed.job.status is IngestionStatus.SUCCEEDED
    assert completed.job.progress == 100
    assert completed.version.status is DocumentVersionStatus.CHUNKED
    assert completed.version.chunk_count == 1
    assert completed.version.chunk_manifest_key in store.objects
    manifest = store.objects[completed.version.chunk_manifest_key or ""].decode("utf-8")
    assert '"parser_name":"markdown-it-py"' in manifest
    assert '"text":"Guide\\n\\nStable content"' in manifest

    assert processor.process(coordinator.bundle.job.id, worker_id="worker-2") is None


def test_processor_retries_transient_object_store_failure_without_exposing_details() -> None:
    coordinator = CoordinatorFake(make_bundle())
    store = ObjectStoreFake()
    store.get_error = ObjectStoreError("internal endpoint detail", retryable=True)
    processor = IngestionProcessor(
        coordinator=coordinator,
        object_store=store,
        parser_registry=ParserRegistry.default(),
        chunker=StructureAwareChunker(),
        lease_seconds=600,
        retry_base_seconds=10,
        clock=lambda: NOW,
    )

    result = processor.process(coordinator.bundle.job.id, worker_id="worker-1")

    assert result is not None
    assert result.job.status is IngestionStatus.RETRY_SCHEDULED
    assert result.job.error_code == "OBJECT_STORE_UNAVAILABLE"
    assert result.job.error_message == "对象存储暂时不可用"
    assert result.version.status is DocumentVersionStatus.UPLOADED


def test_processor_marks_permanent_parse_failure_as_ocr_required() -> None:
    coordinator = CoordinatorFake(make_bundle())
    processor = IngestionProcessor(
        coordinator=coordinator,
        object_store=ObjectStoreFake(),
        parser_registry=ParserRegistry((FailingParser(),)),  # type: ignore[arg-type]
        chunker=StructureAwareChunker(),
        lease_seconds=600,
        retry_base_seconds=10,
        clock=lambda: NOW,
    )

    result = processor.process(coordinator.bundle.job.id, worker_id="worker-1")

    assert result is not None
    assert result.job.status is IngestionStatus.FAILED
    assert result.job.error_code == "OCR_REQUIRED"
    assert result.version.status is DocumentVersionStatus.OCR_REQUIRED


def test_recovery_dispatches_due_and_recovered_jobs_then_records_task_ids() -> None:
    coordinator = CoordinatorFake(make_bundle())
    dispatcher = DispatcherFake()
    coordinator.dispatchable = [coordinator.bundle.job.id, uuid4()]
    recovery = IngestionRecoveryService(
        coordinator=coordinator,
        dispatcher=dispatcher,
        dispatch_stale_seconds=30,
        batch_size=10,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    count = recovery.run()

    assert count == 2
    assert dispatcher.jobs == coordinator.dispatchable
    assert coordinator.dispatched == [
        (job_id, f"task-{job_id}") for job_id in coordinator.dispatchable
    ]
