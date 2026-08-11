from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.common.errors import NotFoundError
from knowagent.documents.application.processor import ChunkManifest
from knowagent.documents.domain.ingestion import DocumentVersionStatus
from knowagent.documents.domain.models import KnowledgeChunk as ParsedKnowledgeChunk
from knowagent.documents.ports import ObjectStore
from knowagent.knowledge.domain.models import KnowledgeChunkDraft
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.retrieval.ports import EmbeddingProvider


class ChunkIngestionService:
    """Persist parsed chunk manifests as knowledge sources and index embeddings.

    Wired after :class:`IngestionProcessor` completes the parsing/chunking
    stage: it reads the chunks-v1 manifest produced by the parser, writes a
    DRAFT knowledge source plus its chunks, runs batch Embedding indexing, and
    advances the document version to ``READY_DRAFT`` only after indexing
    succeeds. Publishing remains a separate reviewer/owner action.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        object_store: ObjectStore,
        embeddings: EmbeddingProvider,
        embedding_batch_size: int,
    ) -> None:
        if embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        self._session_factory = session_factory
        self._object_store = object_store
        self._embeddings = embeddings
        self._embedding_batch_size = embedding_batch_size

    def ingest_chunks(
        self,
        *,
        system_id: UUID,
        document_version_id: UUID,
        manifest_key: str,
        now: datetime,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[UUID, int]:
        """Read the manifest, persist DRAFT knowledge chunks, return source id and chunk count.

        Advances the document version to ``READY_DRAFT`` only after
        :meth:`index_source` succeeds.
        """
        manifest = self._load_manifest(manifest_key)
        drafts = tuple(self._to_draft(chunk) for chunk in manifest.chunks)
        with self._session_factory.begin() as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            version = repository.locked_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if version is None:
                raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
            if version.status is DocumentVersionStatus.READY_DRAFT:
                return self._existing_source(session, system_id, document_version_id)
            if version.status not in {
                DocumentVersionStatus.CHUNKING,
                DocumentVersionStatus.CHUNKED,
            }:
                return self._existing_source(session, system_id, document_version_id)
            existing_source = repository.get_source_by_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if existing_source is None:
                source_record = repository.replace_document_chunks(
                    system_id=system_id,
                    document_version_id=document_version_id,
                    drafts=drafts,
                    now=now,
                )
                source_id = source_record.id
            else:
                source_id = existing_source.id
            chunk_count = repository.source_chunk_count(system_id=system_id, source_id=source_id)
        self._run_indexing(
            system_id=system_id,
            source_id=source_id,
            now=now,
            on_progress=on_progress,
        )
        with self._session_factory.begin() as session:
            version = SqlAlchemyKnowledgeRepository(session).locked_version(
                system_id=system_id, document_version_id=document_version_id
            )
            if version is None:
                raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
            version.status = DocumentVersionStatus.READY_DRAFT
            version.updated_at = now
        return source_id, chunk_count

    def _run_indexing(
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        now: datetime,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.index_source(
                    system_id=system_id,
                    source_id=source_id,
                    now=now,
                    on_progress=on_progress,
                )
            )
        finally:
            loop.close()

    async def index_source(
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        now: datetime,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """Generate and store embeddings for a knowledge source.

        Returns the number of chunks indexed. Provider failures propagate so
        the persistent ingestion job schedules a bounded retry.
        """
        from knowagent.knowledge.application.indexing import KnowledgeIndexService  # noqa: PLC0415

        service = KnowledgeIndexService(
            self._session_factory,
            embeddings=self._embeddings,
            batch_size=self._embedding_batch_size,
        )
        summary = await service.index_source(
            system_id=system_id,
            source_id=source_id,
            now=now,
            on_batch=on_progress,
        )
        return summary.chunk_count

    def _load_manifest(self, manifest_key: str) -> ChunkManifest:
        content = self._object_store.get(key=manifest_key)
        return ChunkManifest.model_validate_json(content)

    @staticmethod
    def _to_draft(chunk: ParsedKnowledgeChunk) -> KnowledgeChunkDraft:
        return KnowledgeChunkDraft(
            ordinal=chunk.ordinal,
            text=chunk.text,
            retrieval_text=chunk.text,
            token_count=chunk.token_count,
            structure_path=chunk.structure_path,
            locators=chunk.locators,
        )

    @staticmethod
    def _existing_source(
        session: Session, system_id: UUID, document_version_id: UUID
    ) -> tuple[UUID, int]:
        repository = SqlAlchemyKnowledgeRepository(session)
        source = repository.get_source_by_version(
            system_id=system_id, document_version_id=document_version_id
        )
        if source is None:
            return UUID(int=0), 0
        count = repository.source_chunk_count(system_id=system_id, source_id=source.id)
        return source.id, count
