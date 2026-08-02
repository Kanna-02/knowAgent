from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersion,
    DocumentVersionStatus,
)
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
)
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.application.publication import KnowledgePublicationService
from knowagent.knowledge.domain.models import KnowledgeChunkDraft, PublicationStatus
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


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


def draft(version_id: UUID, document_id: UUID, text: str) -> KnowledgeChunkDraft:
    return KnowledgeChunkDraft(
        ordinal=0,
        text=text,
        token_count=3,
        structure_path=("Overview",),
        locators=(
            {
                "document_id": document_id,
                "document_version_id": version_id,
                "source_type": "markdown",
                "block_index": 0,
                "heading_path": ("Overview",),
                "paragraph_start": 1,
                "paragraph_end": 1,
                "line_start": 1,
                "line_end": 1,
            },
        ),
    )


def test_publish_switches_current_version_and_retires_previous_chunks() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, first_version_id = add_ready_version(factory, system_id=system_id)
    _, second_version_id = add_ready_version(
        factory,
        system_id=system_id,
        document_id=document_id,
        version_no=2,
    )
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=first_version_id,
        chunks=(draft(first_version_id, document_id, "first version"),),
        now=NOW,
    )
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=second_version_id,
        chunks=(draft(second_version_id, document_id, "second version"),),
        now=NOW,
    )

    service.publish(
        system_id=system_id,
        document_version_id=first_version_id,
        now=NOW,
    )
    service.publish(
        system_id=system_id,
        document_version_id=second_version_id,
        now=NOW,
    )

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        document = repository.get_document(system_id=system_id, document_id=document_id)
        first = repository.get_version(system_id=system_id, document_version_id=first_version_id)
        second = repository.get_version(system_id=system_id, document_version_id=second_version_id)
        visible = repository.list_published_chunks(system_id=system_id, limit=10)

    assert document is not None and document.current_published_version_id == second_version_id
    assert first is not None and first.publish_status is PublicationStatus.RETIRED
    assert second is not None and second.publish_status is PublicationStatus.PUBLISHED
    assert [chunk.text for chunk in visible] == ["second version"]


def test_repository_filters_every_read_by_system_id() -> None:
    factory = make_factory()
    system_a, system_b = uuid4(), uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_a)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_a,
        document_version_id=version_id,
        chunks=(draft(version_id, document_id, "system A only"),),
        now=NOW,
    )
    service.publish(
        system_id=system_a,
        document_version_id=version_id,
        now=NOW,
    )

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        source = repository.get_source_by_version(
            system_id=system_a, document_version_id=version_id
        )
        assert source is not None
        visible_chunk = repository.list_published_chunks(system_id=system_a, limit=10)[0]
        assert repository.get_document(system_id=system_b, document_id=document_id) is None
        assert repository.get_version(system_id=system_b, document_version_id=version_id) is None
        assert repository.get_source(system_id=system_b, source_id=source.id) is None
        assert repository.get_chunk(system_id=system_b, chunk_id=visible_chunk.id) is None
        assert repository.list_published_chunks(system_id=system_b, limit=10) == []


def test_publication_rejects_cross_system_wrong_state_and_empty_chunks() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)

    with pytest.raises(NotFoundError, match="文档版本不存在"):
        service.publish(
            system_id=uuid4(),
            document_version_id=version_id,
            now=NOW,
        )
    with pytest.raises(ValidationError, match="知识片段不能为空"):
        service.replace_draft_chunks(
            system_id=system_id,
            document_version_id=version_id,
            chunks=(),
            now=NOW,
        )
    with pytest.raises(ConflictError, match="尚未生成"):
        service.publish(
            system_id=system_id,
            document_version_id=version_id,
            now=NOW,
        )

    assert document_id


def test_retire_clears_current_pointer_and_hides_chunks() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(draft(version_id, document_id, "retired"),),
        now=NOW,
    )
    service.publish(
        system_id=system_id,
        document_version_id=version_id,
        now=NOW,
    )

    service.retire(
        system_id=system_id,
        document_version_id=version_id,
        now=NOW,
    )

    with factory() as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        document = repository.get_document(system_id=system_id, document_id=document_id)
        version = repository.get_version(system_id=system_id, document_version_id=version_id)
        visible = repository.list_published_chunks(system_id=system_id, limit=10)
    assert document is not None and document.current_published_version_id is None
    assert version is not None and version.publish_status is PublicationStatus.RETIRED
    assert visible == []


def test_replace_draft_chunks_rejects_unknown_version_bad_ordinal_and_locator_scope() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    service = KnowledgePublicationService(factory)
    valid = draft(version_id, document_id, "valid")

    with pytest.raises(NotFoundError, match="文档版本不存在"):
        service.replace_draft_chunks(
            system_id=uuid4(),
            document_version_id=version_id,
            chunks=(valid,),
            now=NOW,
        )
    with pytest.raises(ValidationError, match="序号必须连续"):
        service.replace_draft_chunks(
            system_id=system_id,
            document_version_id=version_id,
            chunks=(valid.model_copy(update={"ordinal": 1}),),
            now=NOW,
        )
    with pytest.raises(ValidationError, match="定位必须属于"):
        service.replace_draft_chunks(
            system_id=system_id,
            document_version_id=version_id,
            chunks=(draft(uuid4(), document_id, "wrong version"),),
            now=NOW,
        )


def test_processing_and_publication_states_are_fail_closed() -> None:
    factory = make_factory()
    system_id = uuid4()
    document_id, version_id = add_ready_version(factory, system_id=system_id)
    with factory.begin() as session:
        record = session.get(DocumentVersionRecord, version_id)
        assert record is not None
        record.status = DocumentVersionStatus.CHUNKED
    service = KnowledgePublicationService(factory)
    chunk = draft(version_id, document_id, "state guarded")

    with pytest.raises(ConflictError, match="完成索引"):
        service.replace_draft_chunks(
            system_id=system_id,
            document_version_id=version_id,
            chunks=(chunk,),
            now=NOW,
        )
    with pytest.raises(ConflictError, match="完成索引"):
        service.publish(
            system_id=system_id,
            document_version_id=version_id,
            now=NOW,
        )

    with factory.begin() as session:
        record = session.get(DocumentVersionRecord, version_id)
        assert record is not None
        record.status = DocumentVersionStatus.READY_DRAFT
    service.replace_draft_chunks(
        system_id=system_id,
        document_version_id=version_id,
        chunks=(chunk,),
        now=NOW,
    )
    service.publish(
        system_id=system_id,
        document_version_id=version_id,
        now=NOW,
    )

    with pytest.raises(ConflictError, match="不可覆盖"):
        service.replace_draft_chunks(
            system_id=system_id,
            document_version_id=version_id,
            chunks=(chunk,),
            now=NOW,
        )
    with pytest.raises(ConflictError, match="只有草稿"):
        service.publish(
            system_id=system_id,
            document_version_id=version_id,
            now=NOW,
        )
    service.retire(
        system_id=system_id,
        document_version_id=version_id,
        now=NOW,
    )
    with pytest.raises(ConflictError, match="只有已发布"):
        service.retire(
            system_id=system_id,
            document_version_id=version_id,
            now=NOW,
        )


def test_retire_unknown_version_is_not_found() -> None:
    service = KnowledgePublicationService(make_factory())

    with pytest.raises(NotFoundError, match="文档版本不存在"):
        service.retire(
            system_id=uuid4(),
            document_version_id=uuid4(),
            now=NOW,
        )


def test_current_published_version_constraint_includes_document_and_system_scope() -> None:
    constraints = DocumentRecord.__table__.foreign_key_constraints
    scoped_pointer = next(
        constraint
        for constraint in constraints
        if constraint.name == "fk_documents_current_published_version_scope"
    )

    assert [column.name for column in scoped_pointer.columns] == [
        "current_published_version_id",
        "id",
        "system_id",
    ]
    assert [element.target_fullname for element in scoped_pointer.elements] == [
        "document_versions.id",
        "document_versions.document_id",
        "document_versions.system_id",
    ]
    assert scoped_pointer.deferrable is True
    assert scoped_pointer.initially == "DEFERRED"
