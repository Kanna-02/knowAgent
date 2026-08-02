from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import BinaryIO, Callable
from uuid import UUID, uuid4

from knowagent.common.errors import ConflictError, ValidationError
from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionBundle,
    IngestionJob,
)
from knowagent.documents.errors import DocumentParseError
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.documents.ports import IngestionRepository, ObjectStore
from knowagent.platform.settings import DocumentProcessingSettings

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
LOGGER = logging.getLogger(__name__)


class DocumentIngestionService:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        repository: IngestionRepository,
        object_store: ObjectStore,
        parser_registry: ParserRegistry,
        settings: DocumentProcessingSettings,
        max_attempts: int,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._parser_registry = parser_registry
        self._settings = settings
        self._max_attempts = max_attempts

    def create_upload(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        actor_id: UUID,
        system_id: UUID,
        document_name: str,
        filename: str,
        media_type: str,
        content: BinaryIO,
        content_length: int,
        sha256: str,
        idempotency_key: str,
        on_persisted: Callable[[IngestionBundle], None] | None = None,
    ) -> IngestionBundle:
        normalized_name = document_name.strip()
        normalized_filename = PurePosixPath(filename.strip()).name
        normalized_media_type = media_type.split(";", maxsplit=1)[0].strip().lower()
        self._validate_upload(
            name=normalized_name,
            filename=normalized_filename,
            media_type=normalized_media_type,
            content_length=content_length,
            sha256=sha256,
            idempotency_key=idempotency_key,
        )
        existing = self._repository.get_by_idempotency_key(
            idempotency_key,
            actor_id=actor_id,
            system_id=system_id,
        )
        if existing is not None:
            self._validate_idempotent_match(
                existing,
                actor_id=actor_id,
                system_id=system_id,
                document_name=normalized_name,
                filename=normalized_filename,
                media_type=normalized_media_type,
                content_length=content_length,
                sha256=sha256,
            )
            if on_persisted is not None:
                on_persisted(existing)
            return existing

        now = datetime.now(UTC)
        document_id = uuid4()
        version_id = uuid4()
        object_key = (
            f"documents/{system_id}/{document_id}/{version_id}/"
            f"source{PurePosixPath(normalized_filename).suffix.lower()}"
        )
        bundle = IngestionBundle(
            document=Document(
                id=document_id,
                system_id=system_id,
                name=normalized_name,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            ),
            version=DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_no=1,
                object_key=object_key,
                filename=normalized_filename,
                media_type=normalized_media_type,
                size_bytes=content_length,
                sha256=sha256,
                status=DocumentVersionStatus.UPLOADED,
                created_by=actor_id,
                created_at=now,
                updated_at=now,
            ),
            job=IngestionJob.new(
                document_version_id=version_id,
                actor_id=actor_id,
                system_id=system_id,
                idempotency_key=idempotency_key,
                max_attempts=self._max_attempts,
                now=now,
            ),
        )
        self._object_store.put(
            key=object_key,
            content=content,
            content_type=normalized_media_type,
            content_length=content_length,
        )
        try:
            stored = self._repository.add(bundle)
            if stored.job.id != bundle.job.id:
                self._delete_best_effort(object_key)
                self._validate_idempotent_match(
                    stored,
                    actor_id=actor_id,
                    system_id=system_id,
                    document_name=normalized_name,
                    filename=normalized_filename,
                    media_type=normalized_media_type,
                    content_length=content_length,
                    sha256=sha256,
                )
            if on_persisted is not None:
                on_persisted(stored)
            return stored
        except Exception:
            self._delete_best_effort(object_key)
            raise

    def _delete_best_effort(self, object_key: str) -> None:
        try:
            self._object_store.delete(key=object_key)
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.exception("orphan object cleanup failed", extra={"object_key": object_key})

    def _validate_upload(  # pylint: disable=too-many-arguments
        self,
        *,
        name: str,
        filename: str,
        media_type: str,
        content_length: int,
        sha256: str,
        idempotency_key: str,
    ) -> None:
        if not name or len(name) > 255:
            raise ValidationError("DOCUMENT_NAME_INVALID", "文档名称不能为空且不能超过 255 字符")
        if not filename or len(filename) > 255:
            raise ValidationError("DOCUMENT_FILENAME_INVALID", "文件名无效")
        if content_length <= 0:
            raise ValidationError("DOCUMENT_EMPTY", "上传文件为空")
        if content_length > self._settings.max_file_bytes:
            raise ValidationError("DOCUMENT_TOO_LARGE", "上传文件超过大小上限")
        if not _SHA256_PATTERN.fullmatch(sha256):
            raise ValidationError("DOCUMENT_CHECKSUM_INVALID", "文件校验值无效")
        if not _IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
            raise ValidationError("IDEMPOTENCY_KEY_INVALID", "幂等键格式无效")
        try:
            self._parser_registry.resolve(filename=filename, media_type=media_type)
        except DocumentParseError as error:
            raise ValidationError("DOCUMENT_FORMAT_UNSUPPORTED", "不支持该文件格式") from error

    @staticmethod
    def _validate_idempotent_match(  # pylint: disable=too-many-arguments
        existing: IngestionBundle,
        *,
        actor_id: UUID,
        system_id: UUID,
        document_name: str,
        filename: str,
        media_type: str,
        content_length: int,
        sha256: str,
    ) -> None:
        version = existing.version
        stored_request = (
            existing.document.created_by,
            existing.document.system_id,
            existing.document.name,
            version.filename,
            version.media_type,
            version.size_bytes,
            version.sha256,
        )
        current_request = (
            actor_id,
            system_id,
            document_name,
            filename,
            media_type,
            content_length,
            sha256,
        )
        if stored_request != current_request:
            raise ConflictError("IDEMPOTENCY_KEY_REUSED", "幂等键已用于不同的上传请求")
