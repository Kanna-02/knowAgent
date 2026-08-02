from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.documents.application.chunking import ChunkingConfig, StructureAwareChunker
from knowagent.documents.application.processor import IngestionProcessor, IngestionRecoveryService
from knowagent.documents.infrastructure.parsers import ParserLimits
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.documents.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIngestionCoordinator,
)
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.object_store import S3ObjectStore
from knowagent.platform.settings import Settings
from knowagent.worker.celery_app import celery_app
from knowagent.worker.dispatcher import CeleryIngestionDispatcher


@dataclass(frozen=True, slots=True)
class _WorkerRuntime:
    settings: Settings
    session_factory: sessionmaker[Session]
    coordinator: SqlAlchemyIngestionCoordinator
    object_store: S3ObjectStore


@lru_cache(maxsize=1)
def _runtime() -> _WorkerRuntime:
    settings = Settings.from_environment()
    storage = settings.object_storage
    if not storage.configured:
        raise RuntimeError("S3 object storage is not configured")
    session_factory = create_session_factory(create_database_engine(settings.database_url))
    return _WorkerRuntime(
        settings=settings,
        session_factory=session_factory,
        coordinator=SqlAlchemyIngestionCoordinator(session_factory),
        object_store=S3ObjectStore.from_settings(storage),
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
