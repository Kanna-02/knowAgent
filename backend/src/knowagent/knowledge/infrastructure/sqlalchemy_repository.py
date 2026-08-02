from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.ingestion import Document, DocumentVersion
from knowagent.documents.domain.models import SourceLocator
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
)
from knowagent.knowledge.domain.models import (
    KnowledgeChunk,
    KnowledgeChunkDraft,
    KnowledgeSource,
    KnowledgeSourceType,
)
from knowagent.knowledge.infrastructure.sqlalchemy_models import (
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
)

# SQLAlchemy's dynamic func namespace triggers a false positive.
# pylint: disable=not-callable


class SqlAlchemyKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_document(self, document: Document) -> Document:
        self._session.add(
            DocumentRecord(
                id=document.id,
                system_id=document.system_id,
                name=document.name,
                current_published_version_id=document.current_published_version_id,
                created_by=document.created_by,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
        )
        self._session.flush()
        return document

    def add_version(self, version: DocumentVersion) -> DocumentVersion:
        self._session.add(
            DocumentVersionRecord(
                id=version.id,
                document_id=version.document_id,
                system_id=version.system_id,
                version_no=version.version_no,
                object_key=version.object_key,
                filename=version.filename,
                media_type=version.media_type,
                size_bytes=version.size_bytes,
                sha256=version.sha256,
                status=version.status,
                publish_status=version.publish_status,
                published_at=version.published_at,
                retired_at=version.retired_at,
                chunk_manifest_key=version.chunk_manifest_key,
                chunk_count=version.chunk_count,
                parser_name=version.parser_name,
                parser_version=version.parser_version,
                schema_version=version.schema_version,
                created_by=version.created_by,
                created_at=version.created_at,
                updated_at=version.updated_at,
            )
        )
        self._session.flush()
        return version

    def get_document(self, *, system_id: UUID, document_id: UUID) -> Document | None:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.system_id == system_id,
            )
        )
        return self._to_document(record) if record is not None else None

    def get_version(self, *, system_id: UUID, document_version_id: UUID) -> DocumentVersion | None:
        record = self._session.scalar(
            select(DocumentVersionRecord).where(
                DocumentVersionRecord.id == document_version_id,
                DocumentVersionRecord.system_id == system_id,
            )
        )
        return self._to_version(record) if record is not None else None

    def get_source(self, *, system_id: UUID, source_id: UUID) -> KnowledgeSource | None:
        record = self._session.scalar(
            select(KnowledgeSourceRecord).where(
                KnowledgeSourceRecord.id == source_id,
                KnowledgeSourceRecord.system_id == system_id,
            )
        )
        return self._to_source(record) if record is not None else None

    def get_source_by_version(
        self, *, system_id: UUID, document_version_id: UUID
    ) -> KnowledgeSource | None:
        record = self._session.scalar(
            select(KnowledgeSourceRecord).where(
                KnowledgeSourceRecord.system_id == system_id,
                KnowledgeSourceRecord.document_version_id == document_version_id,
            )
        )
        return self._to_source(record) if record is not None else None

    def get_chunk(self, *, system_id: UUID, chunk_id: UUID) -> KnowledgeChunk | None:
        record = self._session.scalar(
            select(KnowledgeChunkRecord).where(
                KnowledgeChunkRecord.id == chunk_id,
                KnowledgeChunkRecord.system_id == system_id,
            )
        )
        return self._to_chunk(record) if record is not None else None

    def list_published_chunks(self, *, system_id: UUID, limit: int) -> list[KnowledgeChunk]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        records = self._session.scalars(
            select(KnowledgeChunkRecord)
            .where(
                KnowledgeChunkRecord.system_id == system_id,
                KnowledgeChunkRecord.publish_status == PublicationStatus.PUBLISHED,
            )
            .order_by(KnowledgeChunkRecord.source_id, KnowledgeChunkRecord.ordinal)
            .limit(limit)
        ).all()
        return [self._to_chunk(record) for record in records]

    def locked_version(
        self, *, system_id: UUID, document_version_id: UUID
    ) -> DocumentVersionRecord | None:
        return self._session.scalar(
            select(DocumentVersionRecord)
            .where(
                DocumentVersionRecord.id == document_version_id,
                DocumentVersionRecord.system_id == system_id,
            )
            .with_for_update()
        )

    def locked_document(self, *, system_id: UUID, document_id: UUID) -> DocumentRecord | None:
        return self._session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.id == document_id,
                DocumentRecord.system_id == system_id,
            )
            .with_for_update()
        )

    def locked_document_version(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
    ) -> tuple[DocumentRecord, DocumentVersionRecord] | None:
        candidate = self.get_version(
            system_id=system_id,
            document_version_id=document_version_id,
        )
        if candidate is None:
            return None
        document = self.locked_document(
            system_id=system_id,
            document_id=candidate.document_id,
        )
        if document is None:
            return None
        version = self.locked_version(
            system_id=system_id,
            document_version_id=document_version_id,
        )
        if version is None or version.document_id != document.id:
            return None
        return document, version

    def replace_document_chunks(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        drafts: tuple[KnowledgeChunkDraft, ...],
        now: datetime,
    ) -> KnowledgeSourceRecord:
        source = self._session.scalar(
            select(KnowledgeSourceRecord)
            .where(
                KnowledgeSourceRecord.system_id == system_id,
                KnowledgeSourceRecord.document_version_id == document_version_id,
            )
            .with_for_update()
        )
        if source is None:
            source = KnowledgeSourceRecord(
                system_id=system_id,
                source_type=KnowledgeSourceType.DOCUMENT,
                document_version_id=document_version_id,
                ticket_id=None,
                publish_status=PublicationStatus.DRAFT,
                created_at=now,
                updated_at=now,
            )
            self._session.add(source)
            self._session.flush()
        self._session.execute(
            delete(KnowledgeChunkRecord).where(
                KnowledgeChunkRecord.system_id == system_id,
                KnowledgeChunkRecord.source_id == source.id,
            )
        )
        for draft in drafts:
            self._session.add(
                KnowledgeChunkRecord(
                    system_id=system_id,
                    source_id=source.id,
                    ordinal=draft.ordinal,
                    text=draft.text,
                    token_count=draft.token_count,
                    structure_path=list(draft.structure_path),
                    locators=[locator.model_dump(mode="json") for locator in draft.locators],
                    retrieval_text=draft.retrieval_text or draft.text,
                    embedding_model=draft.embedding_model,
                    embedding_model_version=draft.embedding_model_version,
                    publish_status=PublicationStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                )
            )
        source.updated_at = now
        self._session.flush()
        return source

    def source_chunk_count(self, *, system_id: UUID, source_id: UUID) -> int:
        count = self._session.scalar(
            select(func.count(KnowledgeChunkRecord.id)).where(
                KnowledgeChunkRecord.system_id == system_id,
                KnowledgeChunkRecord.source_id == source_id,
            )
        )
        return int(count or 0)

    def set_publication_status(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        status: PublicationStatus,
        now: datetime,
    ) -> None:
        version = self.locked_version(system_id=system_id, document_version_id=document_version_id)
        if version is None:
            return
        version.publish_status = status
        version.published_at = (
            now if status is PublicationStatus.PUBLISHED else version.published_at
        )
        version.retired_at = now if status is PublicationStatus.RETIRED else None
        version.updated_at = now
        source = self._session.scalar(
            select(KnowledgeSourceRecord)
            .where(
                KnowledgeSourceRecord.system_id == system_id,
                KnowledgeSourceRecord.document_version_id == document_version_id,
            )
            .with_for_update()
        )
        if source is None:
            return
        source.publish_status = status
        source.updated_at = now
        self._session.execute(
            update(KnowledgeChunkRecord)
            .where(
                KnowledgeChunkRecord.system_id == system_id,
                KnowledgeChunkRecord.source_id == source.id,
            )
            .values(publish_status=status, updated_at=now)
        )

    @staticmethod
    def _to_document(record: DocumentRecord) -> Document:
        return Document(
            id=record.id,
            system_id=record.system_id,
            name=record.name,
            created_by=record.created_by,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
            current_published_version_id=record.current_published_version_id,
        )

    @staticmethod
    def _to_version(record: DocumentVersionRecord) -> DocumentVersion:
        return DocumentVersion(
            id=record.id,
            document_id=record.document_id,
            system_id=record.system_id,
            version_no=record.version_no,
            object_key=record.object_key,
            filename=record.filename,
            media_type=record.media_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            status=record.status,
            publish_status=record.publish_status,
            published_at=_aware_or_none(record.published_at),
            retired_at=_aware_or_none(record.retired_at),
            chunk_manifest_key=record.chunk_manifest_key,
            chunk_count=record.chunk_count,
            parser_name=record.parser_name,
            parser_version=record.parser_version,
            schema_version=record.schema_version,
            created_by=record.created_by,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )

    @staticmethod
    def _to_source(record: KnowledgeSourceRecord) -> KnowledgeSource:
        return KnowledgeSource(
            id=record.id,
            system_id=record.system_id,
            source_type=record.source_type,
            document_version_id=record.document_version_id,
            ticket_id=record.ticket_id,
            publish_status=record.publish_status,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )

    @staticmethod
    def _to_chunk(record: KnowledgeChunkRecord) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=record.id,
            system_id=record.system_id,
            source_id=record.source_id,
            ordinal=record.ordinal,
            text=record.text,
            token_count=record.token_count,
            structure_path=tuple(record.structure_path),
            locators=tuple(SourceLocator.model_validate(locator) for locator in record.locators),
            retrieval_text=record.retrieval_text,
            publish_status=record.publish_status,
            embedding_model=record.embedding_model,
            embedding_model_version=record.embedding_model_version,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _aware_or_none(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None
