from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from knowagent.common.errors import ProviderUnavailableError
from knowagent.documents.application.chunking import StructureAwareChunker
from knowagent.documents.domain.ingestion import (
    DocumentVersionStatus,
    IngestionBundle,
    IngestionStage,
)
from knowagent.documents.domain.models import KnowledgeChunk, SourceType
from knowagent.documents.errors import (
    DocumentParseError,
    IngestionLeaseLostError,
    ParseErrorCode,
)
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.documents.ports import (
    ChunkIngestionHook,
    IngestionCoordinator,
    IngestionDispatcher,
    ObjectStore,
)
from knowagent.platform.object_store import ObjectStoreError

LOGGER = logging.getLogger(__name__)


class ChunkManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: UUID
    document_version_id: UUID
    source_type: SourceType
    parser_name: str
    parser_version: str
    schema_version: str
    chunks: tuple[KnowledgeChunk, ...]


class IngestionProcessor:  # pylint: disable=too-few-public-methods
    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        coordinator: IngestionCoordinator,
        object_store: ObjectStore,
        parser_registry: ParserRegistry,
        chunker: StructureAwareChunker,
        lease_seconds: int,
        retry_base_seconds: int,
        clock: Callable[[], datetime] | None = None,
        chunk_ingestion: ChunkIngestionHook | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._object_store = object_store
        self._parser_registry = parser_registry
        self._chunker = chunker
        self._lease_seconds = lease_seconds
        self._retry_base_seconds = retry_base_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._chunk_ingestion = chunk_ingestion

    def process(self, job_id: UUID, *, worker_id: str) -> IngestionBundle | None:
        claimed = self._coordinator.claim(
            job_id,
            owner=worker_id,
            now=self._clock(),
            lease_seconds=self._lease_seconds,
        )
        if claimed is None:
            return None
        attempt = claimed.job.attempt
        try:
            parsing = self._coordinator.advance(
                job_id,
                owner=worker_id,
                attempt=attempt,
                stage=IngestionStage.PARSING,
                progress=20,
                version_status=DocumentVersionStatus.PARSING,
                now=self._clock(),
            )
            content = self._object_store.get(key=parsing.version.object_key)
            parser = self._parser_registry.resolve(
                filename=parsing.version.filename,
                media_type=parsing.version.media_type,
            )
            parsed = parser.parse(
                content=content,
                document_id=parsing.document.id,
                document_version_id=parsing.version.id,
            )
            self._coordinator.advance(
                job_id,
                owner=worker_id,
                attempt=attempt,
                stage=IngestionStage.CHUNKING,
                progress=70,
                version_status=DocumentVersionStatus.CHUNKING,
                now=self._clock(),
            )
            chunks = self._chunker.chunk(parsed)
            manifest = ChunkManifest(
                document_id=parsed.document_id,
                document_version_id=parsed.document_version_id,
                source_type=parsed.source_type,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
                schema_version=parsed.schema_version,
                chunks=chunks,
            )
            manifest_content = manifest.model_dump_json().encode("utf-8")
            manifest_key = str(PurePosixPath(parsing.version.object_key).parent / "chunks-v1.json")
            self._object_store.put(
                key=manifest_key,
                content=BytesIO(manifest_content),
                content_type="application/json",
                content_length=len(manifest_content),
            )
            final_version_status = DocumentVersionStatus.CHUNKED
            if self._chunk_ingestion is not None:

                def on_embedding_progress(completed: int, total: int) -> None:
                    if total <= 0:
                        return
                    progress = 70 + min(25, max(1, completed * 25 // total))
                    self._coordinator.advance(
                        job_id,
                        owner=worker_id,
                        attempt=attempt,
                        stage=IngestionStage.CHUNKING,
                        progress=progress,
                        version_status=DocumentVersionStatus.CHUNKING,
                        now=self._clock(),
                    )

                self._chunk_ingestion.ingest_chunks(
                    system_id=parsing.version.system_id,
                    document_version_id=parsing.version.id,
                    manifest_key=manifest_key,
                    now=self._clock(),
                    on_progress=on_embedding_progress,
                )
                final_version_status = DocumentVersionStatus.READY_DRAFT
            completed = self._coordinator.complete(
                job_id,
                owner=worker_id,
                attempt=attempt,
                manifest_key=manifest_key,
                chunk_count=len(chunks),
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
                schema_version=parsed.schema_version,
                now=self._clock(),
                version_status=final_version_status,
            )
            return completed
        except IngestionLeaseLostError:
            LOGGER.warning("ingestion lease lost", extra={"job_id": str(job_id)})
            return None
        except DocumentParseError as error:
            return self._fail_safely(
                job_id,
                owner=worker_id,
                attempt=attempt,
                error_code=error.code.value,
                error_message=error.message,
                retryable=False,
                version_status=(
                    DocumentVersionStatus.OCR_REQUIRED
                    if error.code is ParseErrorCode.OCR_REQUIRED
                    else DocumentVersionStatus.FAILED
                ),
                now=self._clock(),
                retry_base_seconds=self._retry_base_seconds,
            )
        except ObjectStoreError as error:
            return self._fail_safely(
                job_id,
                owner=worker_id,
                attempt=attempt,
                error_code="OBJECT_STORE_UNAVAILABLE",
                error_message=("对象存储暂时不可用" if error.retryable else "对象存储请求失败"),
                retryable=error.retryable,
                version_status=DocumentVersionStatus.FAILED,
                now=self._clock(),
                retry_base_seconds=self._retry_base_seconds,
            )
        except ProviderUnavailableError:
            return self._fail_safely(
                job_id,
                owner=worker_id,
                attempt=attempt,
                error_code="EMBEDDING_UNAVAILABLE",
                error_message="向量索引服务暂时不可用",
                retryable=True,
                version_status=DocumentVersionStatus.FAILED,
                now=self._clock(),
                retry_base_seconds=self._retry_base_seconds,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.exception("ingestion job failed", extra={"job_id": str(job_id)})
            return self._fail_safely(
                job_id,
                owner=worker_id,
                attempt=attempt,
                error_code="INGESTION_INTERNAL_ERROR",
                error_message="文档处理暂时失败",
                retryable=True,
                version_status=DocumentVersionStatus.FAILED,
                now=self._clock(),
                retry_base_seconds=self._retry_base_seconds,
            )

    def _fail_safely(  # pylint: disable=too-many-arguments
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
    ) -> IngestionBundle | None:
        try:
            return self._coordinator.fail(
                job_id,
                owner=owner,
                attempt=attempt,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                version_status=version_status,
                now=now,
                retry_base_seconds=retry_base_seconds,
            )
        except IngestionLeaseLostError:
            LOGGER.warning("ingestion lease lost", extra={"job_id": str(job_id)})
            return None


class IngestionRecoveryService:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        coordinator: IngestionCoordinator,
        dispatcher: IngestionDispatcher,
        dispatch_stale_seconds: int,
        batch_size: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._dispatcher = dispatcher
        self._dispatch_stale_seconds = dispatch_stale_seconds
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> int:
        now = self._clock()
        job_ids = self._coordinator.recover_and_find_dispatchable(
            now=now,
            stale_before=now - timedelta(seconds=self._dispatch_stale_seconds),
            limit=self._batch_size,
        )
        dispatched = 0
        for job_id in job_ids:
            try:
                task_id = self._dispatcher.enqueue(job_id)
            except Exception:  # pylint: disable=broad-exception-caught
                LOGGER.exception("ingestion dispatch failed", extra={"job_id": str(job_id)})
                continue
            self._coordinator.mark_dispatched(job_id, celery_task_id=task_id, now=now)
            dispatched += 1
        return dispatched
