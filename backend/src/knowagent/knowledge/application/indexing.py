from __future__ import annotations

from collections.abc import Callable
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

    async def index_source(  # pylint: disable=too-many-locals
        self,
        *,
        system_id: UUID,
        source_id: UUID,
        now: datetime,
        on_batch: Callable[[int, int], None] | None = None,
    ) -> KnowledgeIndexSummary:
        with self._session_factory() as session:
            all_chunks = SqlAlchemyKnowledgeRepository(session).list_source_chunks(
                system_id=system_id,
                source_id=source_id,
            )
        if not all_chunks:
            raise NotFoundError("KNOWLEDGE_SOURCE_NOT_FOUND", "知识来源不存在")

        existing_contract = next(
            (
                EmbeddingBatch(
                    model=chunk.embedding_model or "",
                    model_version=chunk.embedding_model_version or "",
                    dimension=len(chunk.embedding or ()),
                    normalized=True,
                    vectors=(chunk.embedding or (),),
                )
                for chunk in all_chunks
                if chunk.embedding is not None
            ),
            None,
        )
        chunks = [chunk for chunk in all_chunks if chunk.embedding is None]
        if not chunks:
            if existing_contract is None:
                raise ProviderUnavailableError("embedding")
            return KnowledgeIndexSummary(
                source_id=source_id,
                chunk_count=len(all_chunks),
                model=existing_contract.model,
                model_version=existing_contract.model_version,
                dimension=existing_contract.dimension,
            )

        contract = existing_contract
        completed = len(all_chunks) - len(chunks)
        for offset in range(0, len(chunks), self._batch_size):
            chunk_batch = chunks[offset : offset + self._batch_size]
            embedding_batch = await self._embeddings.embed(
                texts=tuple(chunk.retrieval_text for chunk in chunk_batch)
            )
            self._validate_batch(
                embedding_batch,
                expected_count=len(chunk_batch),
                previous=contract,
            )
            updates = tuple(
                ChunkEmbeddingUpdate(chunk_id=chunk.id, vector=vector)
                for chunk, vector in zip(chunk_batch, embedding_batch.vectors, strict=True)
            )
            if contract is None:
                contract = embedding_batch
            with self._session_factory.begin() as session:
                updated = SqlAlchemyKnowledgeRepository(session).set_chunk_embeddings(
                    system_id=system_id,
                    source_id=source_id,
                    updates=updates,
                    model=contract.model,
                    model_version=contract.model_version,
                    now=now,
                )
                if updated != len(updates):
                    raise ConflictError(
                        "KNOWLEDGE_INDEX_CHANGED",
                        "知识片段在索引期间发生变化，请重试",
                    )
            completed += len(updates)
            if on_batch is not None:
                on_batch(completed, len(all_chunks))

        if contract is None:
            raise ProviderUnavailableError("embedding")
        return KnowledgeIndexSummary(
            source_id=source_id,
            chunk_count=len(all_chunks),
            model=contract.model,
            model_version=contract.model_version,
            dimension=contract.dimension,
        )

    @staticmethod
    def _validate_batch(
        batch: EmbeddingBatch,
        *,
        expected_count: int,
        previous: EmbeddingBatch | None,
    ) -> None:
        if len(batch.vectors) != expected_count:
            raise ProviderUnavailableError("embedding")
        if previous is None:
            return
        if (
            batch.model != previous.model
            or batch.model_version != previous.model_version
            or batch.dimension != previous.dimension
            or batch.normalized != previous.normalized
        ):
            raise ProviderUnavailableError("embedding")
