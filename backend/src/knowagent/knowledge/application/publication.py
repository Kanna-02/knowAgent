from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.ingestion import DocumentVersionStatus
from knowagent.knowledge.domain.models import KnowledgeChunkDraft
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)


class KnowledgePublicationService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def replace_draft_chunks(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        chunks: tuple[KnowledgeChunkDraft, ...],
        now: datetime,
    ) -> None:
        if not chunks:
            raise ValidationError("KNOWLEDGE_CHUNKS_EMPTY", "知识片段不能为空")
        if [chunk.ordinal for chunk in chunks] != list(range(len(chunks))):
            raise ValidationError("KNOWLEDGE_CHUNK_ORDINAL_INVALID", "知识片段序号必须连续")
        with self._session_factory.begin() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            version = repository.locked_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if version is None:
                raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
            if version.status is not DocumentVersionStatus.READY_DRAFT:
                raise ConflictError(
                    "DOCUMENT_VERSION_NOT_READY",
                    "只有已完成索引的草稿版本可以写入知识片段",
                )
            if version.publish_status is not PublicationStatus.DRAFT:
                raise ConflictError(
                    "DOCUMENT_VERSION_IMMUTABLE",
                    "已发布或已退役版本不可覆盖知识片段",
                )
            for chunk in chunks:
                for locator in chunk.locators:
                    if (
                        locator.document_id != version.document_id
                        or locator.document_version_id != version.id
                    ):
                        raise ValidationError(
                            "KNOWLEDGE_LOCATOR_SCOPE_MISMATCH",
                            "知识片段定位必须属于目标文档版本",
                        )
            repository.replace_document_chunks(
                system_id=system_id,
                document_version_id=document_version_id,
                drafts=chunks,
                now=now,
            )

    def publish(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        now: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            locked = repository.locked_document_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if locked is None:
                raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
            document, version = locked
            if version.status is not DocumentVersionStatus.READY_DRAFT:
                raise ConflictError("DOCUMENT_VERSION_NOT_READY", "文档版本尚未完成索引，不能发布")
            if version.publish_status is not PublicationStatus.DRAFT:
                raise ConflictError("DOCUMENT_VERSION_NOT_PUBLISHABLE", "只有草稿版本可以发布")
            source = repository.get_source_by_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if (
                source is None
                or repository.source_chunk_count(system_id=system_id, source_id=source.id) == 0
            ):
                raise ConflictError("DOCUMENT_VERSION_HAS_NO_KNOWLEDGE", "文档版本尚未生成知识片段")
            previous_id = document.current_published_version_id
            if previous_id is not None and previous_id != document_version_id:
                repository.set_publication_status(
                    system_id=system_id,
                    document_version_id=previous_id,
                    status=PublicationStatus.RETIRED,
                    now=now,
                )
            repository.set_publication_status(
                system_id=system_id,
                document_version_id=document_version_id,
                status=PublicationStatus.PUBLISHED,
                now=now,
            )
            document.current_published_version_id = document_version_id
            document.updated_at = now

    def retire(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        now: datetime,
    ) -> None:
        with self._session_factory.begin() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            locked = repository.locked_document_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if locked is None:
                raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
            document, version = locked
            if version.publish_status is not PublicationStatus.PUBLISHED:
                raise ConflictError("DOCUMENT_VERSION_NOT_RETIRABLE", "只有已发布版本可以退役")
            repository.set_publication_status(
                system_id=system_id,
                document_version_id=document_version_id,
                status=PublicationStatus.RETIRED,
                now=now,
            )
            if document.current_published_version_id == document_version_id:
                document.current_published_version_id = None
                document.updated_at = now
