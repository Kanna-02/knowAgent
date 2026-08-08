from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from knowagent.documents.domain.ingestion import IngestionStatus
from knowagent.notifications.domain.models import NotificationDeliveryStatus
from knowagent.platform.settings import DocumentProcessingSettings, IngestionSettings
from knowagent.worker import tasks


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
    routes = tasks.celery_app.conf.task_routes
    schedule = tasks.celery_app.conf.beat_schedule

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
