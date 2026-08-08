from __future__ import annotations

from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]

from knowagent.worker.celery_app import celery_app


class CeleryIngestionDispatcher:  # pylint: disable=too-few-public-methods
    def __init__(self, application: Celery = celery_app) -> None:
        self._application = application

    def enqueue(self, job_id: UUID) -> str:
        result = self._application.send_task(
            "knowagent.ingestion.process",
            args=[str(job_id)],
            queue="ingestion",
        )
        return str(result.id)

    @property
    def broker_url(self) -> str:
        return str(self._application.conf.broker_url)


class CeleryNotificationDispatcher:  # pylint: disable=too-few-public-methods
    def __init__(self, application: Celery = celery_app) -> None:
        self._application = application

    def enqueue(self, delivery_id: UUID) -> str:
        result = self._application.send_task(
            "knowagent.notification.deliver",
            args=[str(delivery_id)],
            queue="notification",
        )
        return str(result.id)
