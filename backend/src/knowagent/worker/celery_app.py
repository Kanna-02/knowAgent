from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

from knowagent.platform.settings import Settings


def build_celery_app(settings: Settings) -> Celery:
    application = Celery(
        "knowagent",
        broker=settings.redis_url,
        include=["knowagent.worker.tasks"],
    )
    application.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=False,
        task_ignore_result=True,
        task_soft_time_limit=settings.ingestion.soft_time_limit_seconds,
        task_time_limit=settings.ingestion.hard_time_limit_seconds,
        broker_connection_retry_on_startup=True,
        task_routes={
            "knowagent.ingestion.process": {"queue": "ingestion"},
            "knowagent.ingestion.recover": {"queue": "ingestion"},
        },
        beat_schedule={
            "recover-ingestion-jobs": {
                "task": "knowagent.ingestion.recover",
                "schedule": 30.0,
            }
        },
    )
    return application


celery_app = build_celery_app(Settings.from_environment())
