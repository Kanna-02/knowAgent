from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.common.errors import ConflictError, NotFoundError
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersion,
    DocumentVersionStatus,
)
from knowagent.documents.domain.models import KnowledgeChunk, SourceLocator, SourceType
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.application.publication import KnowledgePublicationService
from knowagent.knowledge.domain.models import KnowledgeChunkDraft
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def make_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_ready_version(
    factory: sessionmaker[Session],
    *,
    system_id: UUID,
    document_id: UUID | None = None,
    version_no: int = 1,
) -> tuple[UUID, UUID]:
    actor_id = uuid4()
    resolved_document_id = document_id or uuid4()
    version_id = uuid4()
    with factory.begin() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        if document_id is None:
            repository.add_document(
                Document(
                    id=resolved_document_id,
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
                document_id=resolved_document_id,
                system_id=system_id,
                version_no=version_no,
                object_key=f"documents/{system_id}/{version_id}/source.md",
                filename="guide.md",
                media_type="text/markdown",
                size_bytes=8,
                sha256=f"{version_no}" * 64,
                status=DocumentVersionStatus.READY_DRAFT,
                publish_status=PublicationStatus.DRAFT,
                created_by=actor_id,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return resolved_document_id, version_id


def _draft(version_id: UUID, document_id: UUID, text: str, ordinal: int = 0) -> KnowledgeChunkDraft:
    locator = SourceLocator(
        document_id=document_id,
        document_version_id=version_id,
        source_type=SourceType.MARKDOWN,
        block_index=ordinal,
        heading_path=("Overview",),
        paragraph_start=1,
        paragraph_end=1,
        line_start=1,
        line_end=1,
    )
    chunk = KnowledgeChunk(
        ordinal=ordinal,
        text=text,
        token_count=4,
        structure_path=("Overview",),
        locators=(locator,),
    )
    return KnowledgeChunkDraft(
        ordinal=chunk.ordinal,
        text=chunk.text,
        token_count=chunk.token_count,
        structure_path=chunk.structure_path,
        locators=chunk.locators,
    )


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def test_publish_marks_version_published_and_sets_current_pointer() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(_draft(version_id, document_id, "v1 content"),),
        now=NOW,
    )

    service.publish(system_id=system_id, document_version_id=version_id, now=NOW)

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        document = repository.get_document(system_id=system_id, document_id=document_id)
        version = repository.get_version(system_id=system_id, document_version_id=version_id)
        published = repository.list_published_chunks(system_id=system_id, limit=10)

    assert document is not None
    assert document.current_published_version_id == version_id
    assert version is not None
    assert version.publish_status is PublicationStatus.PUBLISHED
    assert version.published_at == NOW
    assert [chunk.text for chunk in published] == ["v1 content"]


def test_publish_new_version_retires_previous_and_switches_pointer() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, first = add_ready_version(factory, system_id=system_id)
    _, second = add_ready_version(
        factory, system_id=system_id, document_id=document_id, version_no=2
    )
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=first,
        chunks=(_draft(first, document_id, "v1"),),
        now=NOW,
    )
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=second,
        chunks=(_draft(second, document_id, "v2"),),
        now=NOW,
    )

    service.publish(system_id=system_id, document_version_id=first, now=NOW)
    service.publish(system_id=system_id, document_version_id=second, now=NOW + timedelta(hours=1))

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        document = repository.get_document(system_id=system_id, document_id=document_id)
        v1 = repository.get_version(system_id=system_id, document_version_id=first)
        v2 = repository.get_version(system_id=system_id, document_version_id=second)
        published = repository.list_published_chunks(system_id=system_id, limit=10)

    assert document is not None
    assert document.current_published_version_id == second
    assert v1 is not None and v1.publish_status is PublicationStatus.RETIRED
    assert v2 is not None and v2.publish_status is PublicationStatus.PUBLISHED
    assert [chunk.text for chunk in published] == ["v2"]


def test_publish_rejects_version_with_no_chunks() -> None:
    factory = make_factory()
    system_id = uuid4()
    _, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)

    with pytest.raises(ConflictError, match="尚未生成知识片段"):
        service.publish(system_id=system_id, document_version_id=version_id, now=NOW)


def test_publish_rejects_already_published_version() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(_draft(version_id, document_id, "content"),),
        now=NOW,
    )
    service.publish(system_id=system_id, document_version_id=version_id, now=NOW)

    with pytest.raises(ConflictError, match="只有草稿版本可以发布"):
        service.publish(system_id=system_id, document_version_id=version_id, now=NOW)


def test_publish_unknown_version_raises_not_found() -> None:
    factory = make_factory()
    service = KnowledgePublicationService(factory)

    with pytest.raises(NotFoundError, match="文档版本不存在"):
        service.publish(system_id=uuid4(), document_version_id=uuid4(), now=NOW)


# ---------------------------------------------------------------------------
# Retire
# ---------------------------------------------------------------------------


def test_retire_published_version_clears_pointer_and_marks_retired() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(_draft(version_id, document_id, "content"),),
        now=NOW,
    )
    service.publish(system_id=system_id, document_version_id=version_id, now=NOW)

    service.retire(
        system_id=system_id, document_version_id=version_id, now=NOW + timedelta(hours=2)
    )

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        document = repository.get_document(system_id=system_id, document_id=document_id)
        version = repository.get_version(system_id=system_id, document_version_id=version_id)
        published = repository.list_published_chunks(system_id=system_id, limit=10)

    assert document is not None
    assert document.current_published_version_id is None
    assert version is not None
    assert version.publish_status is PublicationStatus.RETIRED
    assert version.retired_at == NOW + timedelta(hours=2)
    assert published == []


def test_retire_rejects_draft_version() -> None:
    factory = make_factory()
    system_id = uuid4()
    _, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)

    with pytest.raises(ConflictError, match="只有已发布版本可以退役"):
        service.retire(system_id=system_id, document_version_id=version_id, now=NOW)


def test_retire_rejects_already_retired_version() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(_draft(version_id, document_id, "content"),),
        now=NOW,
    )
    service.publish(system_id=system_id, document_version_id=version_id, now=NOW)
    service.retire(
        system_id=system_id, document_version_id=version_id, now=NOW + timedelta(hours=1)
    )

    with pytest.raises(ConflictError, match="只有已发布版本可以退役"):
        service.retire(
            system_id=system_id, document_version_id=version_id, now=NOW + timedelta(hours=2)
        )


def test_retire_unknown_version_raises_not_found() -> None:
    factory = make_factory()
    service = KnowledgePublicationService(factory)

    with pytest.raises(NotFoundError, match="文档版本不存在"):
        service.retire(system_id=uuid4(), document_version_id=uuid4(), now=NOW)


def test_cross_system_access_returns_not_found() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(_draft(version_id, document_id, "content"),),
        now=NOW,
    )
    service.publish(system_id=system_id, document_version_id=version_id, now=NOW)

    other = uuid4()
    with pytest.raises(NotFoundError):
        service.retire(system_id=other, document_version_id=version_id, now=NOW)
    with pytest.raises(NotFoundError):
        service.publish(system_id=other, document_version_id=version_id, now=NOW)
