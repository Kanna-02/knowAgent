from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore[import-untyped]

from knowagent.common.errors import ProviderUnavailableError
from knowagent.documents.domain.ingestion import IngestionStage, IngestionStatus
from knowagent.knowledge.domain.models import KnowledgeIndexBatchSummary
from knowagent.notifications.domain.models import NotificationDeliveryStatus
from knowagent.platform.settings import DocumentProcessingSettings, IngestionSettings
from knowagent.worker import tasks
from knowagent.worker.celery_app import celery_app


def runtime_stub() -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(
            document_processing=DocumentProcessingSettings(),
            ingestion=IngestionSettings(),
        ),
        coordinator=object(),
        object_store=object(),
        chunk_ingestion=object(),
    )


def batch_runtime_stub(coordinator: object, chunk_ingestion: object) -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(
            document_processing=DocumentProcessingSettings(),
            ingestion=SimpleNamespace(lease_seconds=900, retry_base_seconds=30),
        ),
        coordinator=coordinator,
        object_store=object(),
        chunk_ingestion=chunk_ingestion,
    )


def batch_bundle() -> SimpleNamespace:
    return SimpleNamespace(
        job=SimpleNamespace(attempt=1),
        version=SimpleNamespace(
            system_id=uuid4(),
            id=uuid4(),
            chunk_manifest_key="documents/chunks-v1.json",
            chunk_count=2,
            parser_name="markdown-it-py",
            parser_version="4.2.0",
            schema_version="chunks-v1",
        ),
    )


class BatchCoordinatorFake:
    def __init__(self, bundle: SimpleNamespace) -> None:
        self.bundle = bundle
        self.claimed: tuple[UUID, str, int] | None = None
        self.advanced: list[int] = []
        self.completed: dict[str, object] | None = None
        self.released = False
        self.failed: dict[str, object] | None = None
        self.dispatched: list[tuple[UUID, str]] = []

    def claim_continuation(
        self,
        job_id: UUID,
        *,
        owner: str,
        now: object,
        lease_seconds: int,
    ) -> SimpleNamespace:
        del now
        self.claimed = (job_id, owner, lease_seconds)
        return self.bundle

    def advance(
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        stage: IngestionStage,
        progress: int,
        version_status: object,
        now: object,
    ) -> SimpleNamespace:
        del job_id, owner, attempt, stage, version_status, now
        self.advanced.append(progress)
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
        now: object,
        version_status: object,
    ) -> SimpleNamespace:
        del job_id, owner, attempt, now, version_status
        self.completed = {
            "manifest_key": manifest_key,
            "chunk_count": chunk_count,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "schema_version": schema_version,
        }
        return SimpleNamespace(job=SimpleNamespace(status=IngestionStatus.SUCCEEDED))

    def release_for_continuation(
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        now: object,
    ) -> SimpleNamespace:
        del job_id, owner, attempt, now
        self.released = True
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
        version_status: object,
        now: object,
        retry_base_seconds: int,
    ) -> SimpleNamespace:
        del job_id, owner, attempt, version_status, now, retry_base_seconds
        self.failed = {
            "error_code": error_code,
            "error_message": error_message,
            "retryable": retryable,
        }
        return SimpleNamespace(job=SimpleNamespace(status=IngestionStatus.RETRY_SCHEDULED))

    def mark_dispatched(self, job_id: UUID, *, celery_task_id: str, now: object) -> None:
        del now
        self.dispatched.append((job_id, celery_task_id))


class BatchChunkFake:
    def __init__(
        self,
        *,
        summary: KnowledgeIndexBatchSummary | None = None,
        error: Exception | None = None,
    ) -> None:
        self.summary = summary
        self.error = error
        self.source_ids: list[UUID] = []

    def source_id_for_version(self, *, system_id: object, document_version_id: object) -> UUID:
        del system_id, document_version_id
        source_id = uuid4()
        self.source_ids.append(source_id)
        return source_id

    def index_next_batch(self, **_: object) -> KnowledgeIndexBatchSummary:
        if self.error is not None:
            raise self.error
        if self.summary is None:
            raise AssertionError("summary is not configured")
        return self.summary


class DispatcherFake:
    instances: list[DispatcherFake] = []

    def __init__(self, application: object) -> None:
        del application
        self.enqueued: list[UUID] = []
        self.instances.append(self)

    def enqueue_batch(self, job_id: UUID) -> str:
        self.enqueued.append(job_id)
        return f"task-{job_id}"


def test_process_ingestion_builds_processor_and_returns_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    captured: dict[str, object] = {}

    class ProcessorFake:
        def __init__(self, **options: object) -> None:
            captured.update(options)

        def process(self, value: UUID, *, worker_id: str) -> SimpleNamespace:
            captured["job_id"] = value
            captured["worker_id"] = worker_id
            return SimpleNamespace(job=SimpleNamespace(status=IngestionStatus.SUCCEEDED))

    monkeypatch.setattr(tasks, "_runtime", runtime_stub)
    monkeypatch.setattr(tasks, "IngestionProcessor", ProcessorFake)

    result = tasks.process_ingestion.run(str(job_id))

    assert result == "SUCCEEDED"
    assert captured["job_id"] == job_id
    assert captured["coordinator"] is not None
    assert str(captured["worker_id"])


def test_process_ingestion_forwards_chunking_checkpoint_to_batch_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()

    class CheckpointCoordinator:
        def __init__(self) -> None:
            self.dispatched: list[tuple[UUID, str]] = []

        def get_job(self, _: UUID) -> SimpleNamespace:
            return SimpleNamespace(
                stage=IngestionStage.CHUNKING,
                status=IngestionStatus.QUEUED,
            )

        def mark_dispatched(self, value: UUID, *, celery_task_id: str, now: object) -> None:
            del now
            self.dispatched.append((value, celery_task_id))

    coordinator = CheckpointCoordinator()

    class ProcessorRaising:
        def __init__(self, **_: object) -> None:
            raise AssertionError("checkpoint must not reparse the document")

    DispatcherFake.instances = []
    monkeypatch.setattr(tasks, "_runtime", lambda: batch_runtime_stub(coordinator, object()))
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)
    monkeypatch.setattr(tasks, "IngestionProcessor", ProcessorRaising)

    result = tasks.process_ingestion.run(str(job_id))

    assert result == "QUEUED"
    assert DispatcherFake.instances[-1].enqueued == [job_id]
    assert coordinator.dispatched == [(job_id, f"task-{job_id}")]


def test_process_ingestion_forwards_due_chunking_retry_to_batch_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()

    class CheckpointCoordinator:
        def __init__(self) -> None:
            self.dispatched: list[tuple[UUID, str]] = []

        def get_job(self, _: UUID) -> SimpleNamespace:
            return SimpleNamespace(
                stage=IngestionStage.CHUNKING,
                status=IngestionStatus.RETRY_SCHEDULED,
                next_retry_at=datetime.now(UTC) - timedelta(seconds=1),
            )

        def mark_dispatched(self, value: UUID, *, celery_task_id: str, now: object) -> None:
            del now
            self.dispatched.append((value, celery_task_id))

    coordinator = CheckpointCoordinator()

    class ProcessorRaising:
        def __init__(self, **_: object) -> None:
            raise AssertionError("checkpoint retry must not reparse the document")

    DispatcherFake.instances = []
    monkeypatch.setattr(tasks, "_runtime", lambda: batch_runtime_stub(coordinator, object()))
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)
    monkeypatch.setattr(tasks, "IngestionProcessor", ProcessorRaising)

    result = tasks.process_ingestion.run(str(job_id))

    assert result == "QUEUED"
    assert DispatcherFake.instances[-1].enqueued == [job_id]
    assert coordinator.dispatched == [(job_id, f"task-{job_id}")]


def test_process_ingestion_does_not_forward_future_chunking_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()

    class CheckpointCoordinator:
        def get_job(self, _: UUID) -> SimpleNamespace:
            return SimpleNamespace(
                stage=IngestionStage.CHUNKING,
                status=IngestionStatus.RETRY_SCHEDULED,
                next_retry_at=datetime.now(UTC) + timedelta(seconds=60),
            )

    class ProcessorFake:
        def __init__(self, **_: object) -> None:
            pass

        def process(self, _: UUID, *, worker_id: str) -> SimpleNamespace:
            del worker_id
            return SimpleNamespace(job=SimpleNamespace(status=IngestionStatus.SUCCEEDED))

    DispatcherFake.instances = []
    monkeypatch.setattr(
        tasks,
        "_runtime",
        lambda: batch_runtime_stub(CheckpointCoordinator(), object()),
    )
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)
    monkeypatch.setattr(tasks, "IngestionProcessor", ProcessorFake)

    result = tasks.process_ingestion.run(str(job_id))

    assert result == "SUCCEEDED"
    assert DispatcherFake.instances == []


def test_process_ingestion_batch_completes_when_last_checkpoint_is_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    summary = KnowledgeIndexBatchSummary(
        source_id=uuid4(),
        total_chunks=2,
        completed_chunks=2,
        complete=True,
        model="bge-m3",
        model_version="2026-08",
        dimension=3,
    )
    coordinator = BatchCoordinatorFake(batch_bundle())
    DispatcherFake.instances = []
    monkeypatch.setattr(
        tasks,
        "_runtime",
        lambda: batch_runtime_stub(coordinator, BatchChunkFake(summary=summary)),
    )
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)

    result = tasks.process_ingestion_batch.run(str(job_id))

    assert result == "SUCCEEDED"
    assert coordinator.advanced == [95]
    assert coordinator.completed == {
        "manifest_key": "documents/chunks-v1.json",
        "chunk_count": 2,
        "parser_name": "markdown-it-py",
        "parser_version": "4.2.0",
        "schema_version": "chunks-v1",
    }
    assert DispatcherFake.instances == []


def test_process_ingestion_batch_releases_lease_and_schedules_next_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    summary = KnowledgeIndexBatchSummary(
        source_id=uuid4(),
        total_chunks=2,
        completed_chunks=1,
        complete=False,
        model="bge-m3",
        model_version="2026-08",
        dimension=3,
    )
    coordinator = BatchCoordinatorFake(batch_bundle())
    DispatcherFake.instances = []
    monkeypatch.setattr(
        tasks,
        "_runtime",
        lambda: batch_runtime_stub(coordinator, BatchChunkFake(summary=summary)),
    )
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)

    result = tasks.process_ingestion_batch.run(str(job_id))

    assert result == "QUEUED"
    assert coordinator.released is True
    assert DispatcherFake.instances[-1].enqueued == [job_id]
    assert coordinator.dispatched == [(job_id, f"task-{job_id}")]


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (ProviderUnavailableError("embedding"), "EMBEDDING_UNAVAILABLE"),
        (SoftTimeLimitExceeded("batch timeout"), "EMBEDDING_UNAVAILABLE"),
    ],
)
def test_process_ingestion_batch_fails_retryably_on_provider_or_timeout(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_code: str,
) -> None:
    job_id = uuid4()
    coordinator = BatchCoordinatorFake(batch_bundle())
    DispatcherFake.instances = []
    monkeypatch.setattr(
        tasks,
        "_runtime",
        lambda: batch_runtime_stub(coordinator, BatchChunkFake(error=error)),
    )
    monkeypatch.setattr(tasks, "CeleryIngestionDispatcher", DispatcherFake)

    result = tasks.process_ingestion_batch.run(str(job_id))

    assert result == "RETRY_SCHEDULED"
    assert coordinator.failed is not None
    assert coordinator.failed["error_code"] == expected_code
    assert coordinator.failed["retryable"] is True


def test_process_ingestion_returns_ignored_when_claim_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProcessorFake:
        def __init__(self, **_: object) -> None:
            pass

        def process(self, _: UUID, *, worker_id: str) -> None:
            assert worker_id
            return None

    monkeypatch.setattr(tasks, "_runtime", runtime_stub)
    monkeypatch.setattr(tasks, "IngestionProcessor", ProcessorFake)

    assert tasks.process_ingestion.run(str(uuid4())) == "IGNORED"


def test_recover_ingestion_uses_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RecoveryFake:
        def __init__(self, **options: object) -> None:
            captured.update(options)

        def run(self) -> int:
            return 3

    monkeypatch.setattr(tasks, "_runtime", runtime_stub)
    monkeypatch.setattr(tasks, "IngestionRecoveryService", RecoveryFake)

    assert tasks.recover_ingestion.run() == 3
    assert captured["dispatch_stale_seconds"] == 60
    assert captured["batch_size"] == 100


def test_notification_tasks_use_dedicated_queue_and_recovery_schedule() -> None:
    routes = celery_app.conf.task_routes
    schedule = celery_app.conf.beat_schedule

    assert routes["knowagent.notification.deliver"] == {"queue": "notification"}
    assert routes["knowagent.notification.recover"] == {"queue": "notification"}
    assert schedule["recover-notification-deliveries"]["task"] == ("knowagent.notification.recover")
    assert schedule["recover-notification-deliveries"]["schedule"] == 15.0


def test_deliver_notification_uses_notification_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_id = uuid4()
    captured: dict[str, object] = {}

    class ProcessorFake:
        def __init__(self, **options: object) -> None:
            captured.update(options)

        async def deliver(self, *, delivery_id: UUID, now: object) -> SimpleNamespace:
            captured["delivery_id"] = delivery_id
            captured["now"] = now
            return SimpleNamespace(status=NotificationDeliveryStatus.DELIVERED)

    monkeypatch.setattr(
        tasks,
        "_notification_runtime",
        lambda: SimpleNamespace(session_factory=object(), provider=object()),
    )
    monkeypatch.setattr(tasks, "NotificationDeliveryProcessor", ProcessorFake)

    assert tasks.deliver_notification.run(str(delivery_id)) == "DELIVERED"
    assert captured["delivery_id"] == delivery_id
