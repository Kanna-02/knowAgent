from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.common.errors import ProviderUnavailableError
from knowagent.documents.application.chunk_ingestion import ChunkIngestionService
from knowagent.documents.application.processor import ChunkManifest
from knowagent.documents.domain.ingestion import Document, DocumentVersion, DocumentVersionStatus
from knowagent.documents.domain.models import KnowledgeChunk, SourceType
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.domain.models import PublicationStatus
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.retrieval.domain.models import EmbeddingBatch

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


class StubEmbeddings:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[tuple[str, ...]] = []

    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch:
        if self.fail:
            raise ProviderUnavailableError("embedding")
        self.batches.append(texts)
        vectors = tuple((float(index + 1), 0.0, 0.0) for index, _ in enumerate(texts))
        return EmbeddingBatch(
            model="bge-m3",
            model_version="2026-08",
            dimension=3,
            normalized=True,
            vectors=vectors,
        )


class FakeObjectStore:
    def __init__(self, chunks: tuple[KnowledgeChunk, ...]) -> None:
        manifest = ChunkManifest(
            document_id=uuid4(),
            document_version_id=uuid4(),
            source_type=SourceType.MARKDOWN,
            parser_name="markdown",
            parser_version="1.0",
            schema_version="chunks-v1",
            chunks=chunks,
        )
        self._content = manifest.model_dump_json().encode("utf-8")

    def put(self, *, key: str, content: BytesIO, content_type: str, content_length: int) -> None:
        raise AssertionError("FakeObjectStore.put should not be called by ChunkIngestionService")

    def get(self, *, key: str) -> bytes:
        return self._content

    def delete(self, *, key: str) -> None:
        raise AssertionError("FakeObjectStore.delete should not be called")


def make_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_version(
    factory: sessionmaker[Session],
    *,
    system_id: UUID,
    status: DocumentVersionStatus = DocumentVersionStatus.CHUNKED,
) -> UUID:
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
                status=status,
                publish_status=PublicationStatus.DRAFT,
                created_by=actor_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return version_id


def parsed_chunks() -> tuple[KnowledgeChunk, ...]:
    return tuple(
        KnowledgeChunk(
            ordinal=index,
            text=text,
            token_count=3,
            structure_path=("Guide",),
            locators=(
                {
                    "document_id": uuid4(),
                    "document_version_id": uuid4(),
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


def load_version_status(
    factory: sessionmaker[Session], *, system_id: UUID, version_id: UUID
) -> DocumentVersionStatus:
    with factory() as session:
        version = SqlAlchemyKnowledgeRepository(session).locked_version(
            system_id=system_id, document_version_id=version_id
        )
    assert version is not None
    return version.status


def load_chunks(factory: sessionmaker[Session], *, system_id: UUID, source_id: UUID) -> list:
    with factory() as session:
        return SqlAlchemyKnowledgeRepository(session).list_source_chunks(
            system_id=system_id, source_id=source_id
        )


def test_ingest_chunks_advances_version_to_ready_draft_and_indexes_embeddings() -> None:
    factory = make_factory()
    system_id = uuid4()
    version_id = seed_version(factory, system_id=system_id)
    embeddings = StubEmbeddings()
    service = ChunkIngestionService(
        session_factory=factory,
        object_store=FakeObjectStore(parsed_chunks()),
        embeddings=embeddings,
        embedding_batch_size=2,
    )

    source_id, chunk_count = service.ingest_chunks(
        system_id=system_id,
        document_version_id=version_id,
        manifest_key="manifests/chunks-v1.json",
        now=NOW,
    )

    assert chunk_count == 3
    assert (
        load_version_status(factory, system_id=system_id, version_id=version_id)
        is DocumentVersionStatus.READY_DRAFT
    )
    assert embeddings.batches == [("第一段", "第二段"), ("第三段",)]
    chunks = load_chunks(factory, system_id=system_id, source_id=source_id)
    assert [chunk.embedding for chunk in chunks] == [
        (1.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ]


def test_ingest_chunks_is_idempotent_when_version_already_ingested() -> None:
    factory = make_factory()
    system_id = uuid4()
    version_id = seed_version(factory, system_id=system_id)
    embeddings = StubEmbeddings()
    service = ChunkIngestionService(
        session_factory=factory,
        object_store=FakeObjectStore(parsed_chunks()),
        embeddings=embeddings,
        embedding_batch_size=2,
    )

    first_source_id, first_count = service.ingest_chunks(
        system_id=system_id,
        document_version_id=version_id,
        manifest_key="manifests/chunks-v1.json",
        now=NOW,
    )
    assert first_count == 3
    assert len(embeddings.batches) == 2

    second_source_id, second_count = service.ingest_chunks(
        system_id=system_id,
        document_version_id=version_id,
        manifest_key="manifests/chunks-v1.json",
        now=NOW,
    )

    assert second_source_id == first_source_id
    assert second_count == 3
    assert len(embeddings.batches) == 2
    assert (
        load_version_status(factory, system_id=system_id, version_id=version_id)
        is DocumentVersionStatus.READY_DRAFT
    )


def test_ingest_chunks_raises_when_embedding_provider_fails_for_persistent_retry() -> None:
    factory = make_factory()
    system_id = uuid4()
    version_id = seed_version(factory, system_id=system_id)
    service = ChunkIngestionService(
        session_factory=factory,
        object_store=FakeObjectStore(parsed_chunks()),
        embeddings=StubEmbeddings(fail=True),
        embedding_batch_size=2,
    )

    with pytest.raises(ProviderUnavailableError):
        service.ingest_chunks(
            system_id=system_id,
            document_version_id=version_id,
            manifest_key="manifests/chunks-v1.json",
            now=NOW,
        )

    assert (
        load_version_status(factory, system_id=system_id, version_id=version_id)
        is DocumentVersionStatus.CHUNKED
    )
    with factory() as session:
        source = SqlAlchemyKnowledgeRepository(session).get_source_by_version(
            system_id=system_id, document_version_id=version_id
        )
    assert source is not None
    chunks = load_chunks(factory, system_id=system_id, source_id=source.id)
    assert len(chunks) == 3
    assert all(chunk.embedding is None for chunk in chunks)

    service._embeddings.fail = False  # noqa: SLF001
    recovered_source_id, recovered_count = service.ingest_chunks(
        system_id=system_id,
        document_version_id=version_id,
        manifest_key="manifests/chunks-v1.json",
        now=NOW,
    )
    assert recovered_source_id == source.id
    assert recovered_count == 3
    assert all(
        chunk.embedding is not None
        for chunk in load_chunks(factory, system_id=system_id, source_id=source.id)
    )


def test_ingest_chunks_rejects_zero_embedding_batch_size() -> None:
    with pytest.raises(ValueError, match="embedding_batch_size"):
        ChunkIngestionService(
            session_factory=make_factory(),
            object_store=FakeObjectStore(parsed_chunks()),
            embeddings=StubEmbeddings(),
            embedding_batch_size=0,
        )


def test_ingest_chunks_raises_when_version_missing() -> None:
    factory = make_factory()
    system_id = uuid4()
    service = ChunkIngestionService(
        session_factory=factory,
        object_store=FakeObjectStore(parsed_chunks()),
        embeddings=StubEmbeddings(),
        embedding_batch_size=2,
    )

    with pytest.raises(Exception, match="文档版本不存在|DOCUMENT_VERSION_NOT_FOUND"):
        service.ingest_chunks(
            system_id=system_id,
            document_version_id=uuid4(),
            manifest_key="manifests/chunks-v1.json",
            now=NOW,
        )
    assert service._embeddings.batches == []  # noqa: SLF001


def test_index_source_propagates_provider_unavailable() -> None:
    factory = make_factory()
    system_id = uuid4()
    version_id = seed_version(factory, system_id=system_id)
    service = ChunkIngestionService(
        session_factory=factory,
        object_store=FakeObjectStore(parsed_chunks()),
        embeddings=StubEmbeddings(fail=True),
        embedding_batch_size=2,
    )

    with pytest.raises(Exception):
        service._run_indexing(system_id=system_id, source_id=uuid4(), now=NOW)  # noqa: SLF001
    assert (
        load_version_status(factory, system_id=system_id, version_id=version_id)
        is DocumentVersionStatus.CHUNKED
    )
