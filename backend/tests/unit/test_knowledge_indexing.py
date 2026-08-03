from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.common.errors import NotFoundError, ProviderUnavailableError
from knowagent.documents.domain.ingestion import Document, DocumentVersion, DocumentVersionStatus
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.application.indexing import KnowledgeIndexService
from knowagent.knowledge.application.publication import KnowledgePublicationService
from knowagent.knowledge.domain.models import (
    ChunkEmbeddingUpdate,
    KnowledgeChunkDraft,
    PublicationStatus,
)
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.retrieval.domain.models import EmbeddingBatch

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


class StubEmbeddings:
    def __init__(self, *, wrong_count: bool = False) -> None:
        self.wrong_count = wrong_count
        self.batches: list[tuple[str, ...]] = []

    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch:
        self.batches.append(texts)
        vectors = tuple((float(index + 1), 0.0, 0.0) for index, _ in enumerate(texts))
        if self.wrong_count:
            vectors = vectors[:-1]
        return EmbeddingBatch(
            model="bge-m3",
            model_version="2026-08",
            dimension=3,
            normalized=True,
            vectors=vectors,
        )


def make_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_chunks(factory: sessionmaker[Session], *, system_id: UUID) -> UUID:
    document_id, version_id, actor_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        repository.add_document(
            Document(
                id=document_id,
                system_id=system_id,
                name="Guide",
                created_by=actor_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        repository.add_version(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                system_id=system_id,
                version_no=1,
                object_key="guide.md",
                filename="guide.md",
                media_type="text/markdown",
                size_bytes=20,
                sha256="a" * 64,
                status=DocumentVersionStatus.READY_DRAFT,
                publish_status=PublicationStatus.DRAFT,
                created_by=actor_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    service = KnowledgePublicationService(factory)
    chunks = tuple(
        KnowledgeChunkDraft(
            ordinal=index,
            text=text,
            token_count=3,
            structure_path=("Guide",),
            locators=(
                {
                    "document_id": document_id,
                    "document_version_id": version_id,
                    "source_type": "markdown",
                    "block_index": index,
                    "heading_path": ("Guide",),
                    "paragraph_start": index + 1,
                    "paragraph_end": index + 1,
                    "line_start": index + 1,
                    "line_end": index + 1,
                },
            ),
        )
        for index, text in enumerate(("第一段", "第二段", "第三段"))
    )
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=chunks,
        now=NOW,
    )
    with factory() as session:
        source = SqlAlchemyKnowledgeRepository(session).get_source_by_version(
            system_id=system_id,
            document_version_id=version_id,
        )
        assert source is not None
        return source.id


@pytest.mark.anyio
async def test_index_source_batches_and_atomically_persists_model_contract() -> None:
    factory = make_factory()
    system_id = uuid4()
    source_id = seed_chunks(factory, system_id=system_id)
    embeddings = StubEmbeddings()
    service = KnowledgeIndexService(factory, embeddings=embeddings, batch_size=2)

    summary = await service.index_source(system_id=system_id, source_id=source_id, now=NOW)

    assert summary.chunk_count == 3
    assert summary.dimension == 3
    assert embeddings.batches == [("第一段", "第二段"), ("第三段",)]
    with factory() as session:
        chunks = SqlAlchemyKnowledgeRepository(session).list_source_chunks(
            system_id=system_id,
            source_id=source_id,
        )
    assert [chunk.embedding for chunk in chunks] == [
        (1.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ]
    assert {chunk.embedding_model for chunk in chunks} == {"bge-m3"}


@pytest.mark.anyio
async def test_index_source_rejects_invalid_provider_count_without_partial_writes() -> None:
    factory = make_factory()
    system_id = uuid4()
    source_id = seed_chunks(factory, system_id=system_id)
    service = KnowledgeIndexService(
        factory,
        embeddings=StubEmbeddings(wrong_count=True),
        batch_size=2,
    )

    with pytest.raises(ProviderUnavailableError):
        await service.index_source(system_id=system_id, source_id=source_id, now=NOW)

    with factory() as session:
        chunks = SqlAlchemyKnowledgeRepository(session).list_source_chunks(
            system_id=system_id,
            source_id=source_id,
        )
    assert all(chunk.embedding is None for chunk in chunks)


@pytest.mark.anyio
async def test_index_source_hides_unknown_or_cross_system_sources() -> None:
    factory = make_factory()
    system_id = uuid4()
    source_id = seed_chunks(factory, system_id=system_id)
    service = KnowledgeIndexService(factory, embeddings=StubEmbeddings(), batch_size=2)

    with pytest.raises(NotFoundError, match="知识来源不存在"):
        await service.index_source(system_id=uuid4(), source_id=source_id, now=NOW)


def test_set_chunk_embeddings_uses_one_bulk_update_for_all_chunks() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 3
    updates = tuple(
        ChunkEmbeddingUpdate(chunk_id=uuid4(), vector=(float(index), 0.0, 0.0))
        for index in range(3)
    )

    updated = SqlAlchemyKnowledgeRepository(session).set_chunk_embeddings(
        system_id=uuid4(),
        source_id=uuid4(),
        updates=updates,
        model="bge-m3",
        model_version="2026-08",
        now=NOW,
    )

    assert updated == 3
    assert session.execute.call_count == 1
    parameters = session.execute.call_args.args[1]
    assert len(parameters) == 3
