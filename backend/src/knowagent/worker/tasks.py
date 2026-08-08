from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.documents.application.chunk_ingestion import ChunkIngestionService
from knowagent.documents.application.chunking import ChunkingConfig, StructureAwareChunker
from knowagent.documents.application.processor import IngestionProcessor, IngestionRecoveryService
from knowagent.documents.infrastructure.parsers import ParserLimits
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.documents.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIngestionCoordinator,
)
from knowagent.notifications.application.delivery import (
    NotificationDeliveryProcessor,
    NotificationPreparationService,
)
from knowagent.notifications.infrastructure.http_provider import HttpNotificationProvider
from knowagent.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.object_store import S3ObjectStore
from knowagent.platform.settings import Settings
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider
from knowagent.worker.celery_app import celery_app
from knowagent.worker.dispatcher import CeleryIngestionDispatcher, CeleryNotificationDispatcher


@dataclass(frozen=True, slots=True)
class _WorkerRuntime:
    settings: Settings
    session_factory: sessionmaker[Session]
    coordinator: SqlAlchemyIngestionCoordinator
    object_store: S3ObjectStore
    chunk_ingestion: ChunkIngestionService


@dataclass(frozen=True, slots=True)
class _NotificationWorkerRuntime:
    settings: Settings
    session_factory: sessionmaker[Session]
    provider: HttpNotificationProvider


@lru_cache(maxsize=1)
def _runtime() -> _WorkerRuntime:
    settings = Settings.from_environment()
    storage = settings.object_storage
    if not storage.configured:
        raise RuntimeError("S3 object storage is not configured")
    session_factory = create_session_factory(create_database_engine(settings.database_url))
    retrieval = settings.retrieval
    embeddings = HttpEmbeddingProvider(
        base_url=retrieval.embedding_base_url,
        model=retrieval.embedding_model,
        timeout_seconds=retrieval.embedding_timeout_seconds,
    )
    chunk_ingestion = ChunkIngestionService(
        session_factory=session_factory,
        object_store=S3ObjectStore.from_settings(storage),
        embeddings=embeddings,
        embedding_batch_size=retrieval.embedding_batch_size,
    )
    return _WorkerRuntime(
        settings=settings,
        session_factory=session_factory,
        coordinator=SqlAlchemyIngestionCoordinator(session_factory),
        object_store=S3ObjectStore.from_settings(storage),
        chunk_ingestion=chunk_ingestion,
    )


@lru_cache(maxsize=1)
def _notification_runtime() -> _NotificationWorkerRuntime:
    settings = Settings.from_environment()
    return _NotificationWorkerRuntime(
        settings=settings,
        session_factory=create_session_factory(create_database_engine(settings.database_url)),
        provider=HttpNotificationProvider(
            environment=os.environ,
            allowed_hosts=settings.notifications.allowed_hosts,
            runtime_environment=settings.environment,
        ),
    )


@celery_app.task(name="knowagent.ingestion.process")  # type: ignore[untyped-decorator]
def process_ingestion(job_id: str) -> str:
    runtime = _runtime()
    settings = runtime.settings
    result = IngestionProcessor(
        coordinator=runtime.coordinator,
        object_store=runtime.object_store,
        parser_registry=ParserRegistry.default(
            ParserLimits.from_settings(settings.document_processing)
        ),
        chunker=StructureAwareChunker(ChunkingConfig.from_settings(settings.document_processing)),
        lease_seconds=settings.ingestion.lease_seconds,
        retry_base_seconds=settings.ingestion.retry_base_seconds,
        chunk_ingestion=runtime.chunk_ingestion,
    ).process(
        UUID(job_id),
        worker_id=f"{socket.gethostname()}:{os.getpid()}",
    )
    return result.job.status.value if result is not None else "IGNORED"


@celery_app.task(name="knowagent.ingestion.recover")  # type: ignore[untyped-decorator]
def recover_ingestion() -> int:
    runtime = _runtime()
    return IngestionRecoveryService(
        coordinator=runtime.coordinator,
        dispatcher=CeleryIngestionDispatcher(celery_app),
        dispatch_stale_seconds=runtime.settings.ingestion.dispatch_stale_seconds,
        batch_size=runtime.settings.ingestion.recovery_batch_size,
    ).run()


@celery_app.task(name="knowagent.notification.deliver")  # type: ignore[untyped-decorator]
def deliver_notification(delivery_id: str) -> str:
    runtime = _notification_runtime()
    result = asyncio.run(
        NotificationDeliveryProcessor(
            session_factory=runtime.session_factory,
            provider=runtime.provider,
        ).deliver(
            delivery_id=UUID(delivery_id),
            now=datetime.now(UTC),
        )
    )
    return result.status.value


@celery_app.task(name="knowagent.notification.recover")  # type: ignore[untyped-decorator]
def recover_notifications() -> int:
    runtime = _notification_runtime()
    now = datetime.now(UTC)
    with runtime.session_factory.begin() as session:
        repository = SqlAlchemyNotificationRepository(session)
        NotificationPreparationService(repository=repository).prepare_pending(
            now=now,
            limit=runtime.settings.notifications.recovery_batch_size,
        )
        delivery_ids = repository.list_due_delivery_ids(
            now=now,
            stale_before=now
            - timedelta(seconds=runtime.settings.notifications.dispatch_stale_seconds),
            limit=runtime.settings.notifications.recovery_batch_size,
        )
    dispatcher = CeleryNotificationDispatcher(celery_app)
    for delivery_id in delivery_ids:
        dispatcher.enqueue(delivery_id)
    return len(delivery_ids)
