from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.common.errors import ConflictError, NotFoundError, ProviderUnavailableError
from knowagent.knowledge.domain.models import ChunkEmbeddingUpdate, KnowledgeIndexSummary
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.retrieval.domain.models import EmbeddingBatch
from knowagent.retrieval.ports import EmbeddingProvider


class KnowledgeIndexService:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        embeddings: EmbeddingProvider,
        batch_size: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("embedding batch_size must be positive")
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._batch_size = batch_size

    async def index_source(
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        now: datetime,
    ) -> KnowledgeIndexSummary:
        with self._session_factory() as session:
            chunks = SqlAlchemyKnowledgeRepository(session).list_source_chunks(
                system_id=system_id,
                source_id=source_id,
            )
        if not chunks:
            raise NotFoundError("KNOWLEDGE_SOURCE_NOT_FOUND", "知识来源不存在")

        batches: list[EmbeddingBatch] = []
        updates: list[ChunkEmbeddingUpdate] = []
        for offset in range(0, len(chunks), self._batch_size):
            chunk_batch = chunks[offset : offset + self._batch_size]
            embedding_batch = await self._embeddings.embed(
                texts=tuple(chunk.retrieval_text for chunk in chunk_batch)
            )
            self._validate_batch(embedding_batch, expected_count=len(chunk_batch), previous=batches)
            batches.append(embedding_batch)
            updates.extend(
                ChunkEmbeddingUpdate(chunk_id=chunk.id, vector=vector)
                for chunk, vector in zip(chunk_batch, embedding_batch.vectors, strict=True)
            )

        contract = batches[0]
        with self._session_factory.begin() as session:
            updated = SqlAlchemyKnowledgeRepository(session).set_chunk_embeddings(
                system_id=system_id,
                source_id=source_id,
                updates=tuple(updates),
                model=contract.model,
                model_version=contract.model_version,
                now=now,
            )
            if updated != len(chunks):
                raise ConflictError(
                    "KNOWLEDGE_INDEX_CHANGED",
                    "知识片段在索引期间发生变化，请重试",
                )
        return KnowledgeIndexSummary(
            source_id=source_id,
            chunk_count=len(chunks),
            model=contract.model,
            model_version=contract.model_version,
            dimension=contract.dimension,
        )

    @staticmethod
    def _validate_batch(
        batch: EmbeddingBatch,
        *,
        expected_count: int,
        previous: list[EmbeddingBatch],
    ) -> None:
        if len(batch.vectors) != expected_count:
            raise ProviderUnavailableError("embedding")
        if not previous:
            return
        first = previous[0]
        if (
            batch.model != first.model
            or batch.model_version != first.model_version
            or batch.dimension != first.dimension
            or batch.normalized != first.normalized
        ):
            raise ProviderUnavailableError("embedding")
