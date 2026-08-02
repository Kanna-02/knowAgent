from __future__ import annotations

from io import BytesIO
from uuid import UUID, uuid4

import pytest

from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.documents.application.ingestion_service import DocumentIngestionService
from knowagent.documents.domain.ingestion import Document, IngestionBundle
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.platform.settings import DocumentProcessingSettings


class IngestionRepositoryFake:
    def __init__(self, events: list[str] | None = None) -> None:
        self.by_key: dict[tuple[UUID, UUID, str], IngestionBundle] = {}
        self.documents: dict[UUID, Document] = {}
        self.events = events

    def get_by_idempotency_key(
        self, key: str, *, actor_id: UUID, system_id: UUID
    ) -> IngestionBundle | None:
        return self.by_key.get((actor_id, system_id, key))

    def add(self, bundle: IngestionBundle) -> IngestionBundle:
        self.documents.setdefault(bundle.document.id, bundle.document)
        self.by_key[(bundle.job.actor_id, bundle.job.system_id, bundle.job.idempotency_key)] = (
            bundle
        )
        return bundle

    def get_document(self, *, system_id: UUID, document_id: UUID) -> Document | None:
        document = self.documents.get(document_id)
        if document is None or document.system_id != system_id:
            return None
        return document

    def next_version_no(self, *, system_id: UUID, document_id: UUID) -> int:
        if self.events is not None:
            self.events.append("next_version_no")
        versions = [
            bundle.version.version_no
            for bundle in self.by_key.values()
            if bundle.document.id == document_id and bundle.document.system_id == system_id
        ]
        return max(versions, default=0) + 1


class FailingRepositoryFake(IngestionRepositoryFake):
    def add(self, bundle: IngestionBundle) -> IngestionBundle:
        del bundle
        raise RuntimeError("database failed")


class ObjectStoreFake:
    def __init__(self, events: list[str] | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0
        self.events = events

    def put(
        self,
        *,
        key: str,
        content: BytesIO,
        content_type: str,
        content_length: int,
    ) -> None:
        del content_type
        payload = content.read()
        assert len(payload) == content_length
        self.objects[key] = payload
        self.put_calls += 1
        if self.events is not None:
            self.events.append("object_put")

    def get(self, *, key: str) -> bytes:
        return self.objects[key]

    def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


def make_service() -> tuple[DocumentIngestionService, IngestionRepositoryFake, ObjectStoreFake]:
    repository = IngestionRepositoryFake()
    object_store = ObjectStoreFake()
    service = DocumentIngestionService(
        repository=repository,
        object_store=object_store,
        parser_registry=ParserRegistry.default(),
        settings=DocumentProcessingSettings(max_file_bytes=128),
        max_attempts=3,
    )
    return service, repository, object_store


def create_upload(
    service: DocumentIngestionService,
    *,
    idempotency_key: str = "upload-001",
    content: bytes = b"# Guide\n\nStable content\n",
) -> IngestionBundle:
    return service.create_upload(
        actor_id=uuid4(),
        system_id=uuid4(),
        document_name="Guide",
        filename="guide.md",
        media_type="text/markdown",
        content=BytesIO(content),
        content_length=len(content),
        sha256="a" * 64 if content.startswith(b"#") else "b" * 64,
        idempotency_key=idempotency_key,
    )


def test_create_upload_persists_object_and_returns_initial_job() -> None:
    service, repository, object_store = make_service()

    bundle = create_upload(service)

    assert bundle.version.object_key in object_store.objects
    assert bundle.version.filename == "guide.md"
    assert bundle.job.progress == 0
    assert list(repository.by_key.values()) == [bundle]


def test_same_idempotency_key_and_payload_returns_existing_without_second_upload() -> None:
    service, _, object_store = make_service()
    actor_id, system_id = uuid4(), uuid4()
    content = b"# Guide\n\nStable content\n"
    arguments: dict[str, UUID | str | int | BytesIO] = {
        "actor_id": actor_id,
        "system_id": system_id,
        "document_name": "Guide",
        "filename": "guide.md",
        "media_type": "text/markdown",
        "content_length": len(content),
        "sha256": "a" * 64,
        "idempotency_key": "upload-001",
    }

    first = service.create_upload(content=BytesIO(content), **arguments)  # type: ignore[arg-type]
    second = service.create_upload(content=BytesIO(content), **arguments)  # type: ignore[arg-type]

    assert second == first
    assert object_store.put_calls == 1


def test_existing_document_upload_creates_next_version_within_same_system() -> None:
    service, _, _ = make_service()
    actor_id, system_id = uuid4(), uuid4()
    first_content = b"# Guide v1\n"
    first = service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_name="Guide",
        filename="guide.md",
        media_type="text/markdown",
        content=BytesIO(first_content),
        content_length=len(first_content),
        sha256="a" * 64,
        idempotency_key="upload-v1",
    )
    second_content = b"# Guide v2\n"

    second = service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_id=first.document.id,
        document_name="Ignored rename",
        filename="guide-v2.md",
        media_type="text/markdown",
        content=BytesIO(second_content),
        content_length=len(second_content),
        sha256="b" * 64,
        idempotency_key="upload-v2",
    )

    assert second.document == first.document
    assert second.version.document_id == first.document.id
    assert second.version.system_id == system_id
    assert second.version.version_no == 2

    with pytest.raises(NotFoundError, match="文档不存在"):
        service.create_upload(
            actor_id=actor_id,
            system_id=uuid4(),
            document_id=first.document.id,
            document_name="Guide",
            filename="guide-v3.md",
            media_type="text/markdown",
            content=BytesIO(second_content),
            content_length=len(second_content),
            sha256="c" * 64,
            idempotency_key="upload-v3",
        )


def test_existing_document_replay_uses_upload_actor_not_document_creator() -> None:
    service, _, object_store = make_service()
    creator_id, uploader_id, system_id = uuid4(), uuid4(), uuid4()
    first_content = b"# Guide v1\n"
    first = service.create_upload(
        actor_id=creator_id,
        system_id=system_id,
        document_name="Guide",
        filename="guide.md",
        media_type="text/markdown",
        content=BytesIO(first_content),
        content_length=len(first_content),
        sha256="a" * 64,
        idempotency_key="upload-v1",
    )
    second_content = b"# Guide v2\n"
    arguments = {
        "actor_id": uploader_id,
        "system_id": system_id,
        "document_id": first.document.id,
        "document_name": "Guide",
        "filename": "guide-v2.md",
        "media_type": "text/markdown",
        "content_length": len(second_content),
        "sha256": "b" * 64,
        "idempotency_key": "upload-v2",
    }

    created = service.create_upload(content=BytesIO(second_content), **arguments)
    replayed = service.create_upload(content=BytesIO(second_content), **arguments)

    assert replayed == created
    assert replayed.job.actor_id == uploader_id
    assert object_store.put_calls == 2


@pytest.mark.parametrize("first_has_document_id", [False, True])
def test_idempotency_key_rejects_switching_between_create_and_new_version(
    first_has_document_id: bool,
) -> None:
    service, _, _ = make_service()
    actor_id, system_id = uuid4(), uuid4()
    base_content = b"# Base\n"
    base = service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_name="Guide",
        filename="base.md",
        media_type="text/markdown",
        content=BytesIO(base_content),
        content_length=len(base_content),
        sha256="a" * 64,
        idempotency_key="base",
    )
    content = b"# Same payload\n"
    first_document_id = base.document.id if first_has_document_id else None
    first = service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_id=first_document_id,
        document_name="Guide",
        filename="same.md",
        media_type="text/markdown",
        content=BytesIO(content),
        content_length=len(content),
        sha256="b" * 64,
        idempotency_key="operation-switch",
    )
    replay_document_id = None if first_has_document_id else first.document.id

    with pytest.raises(ConflictError, match="幂等键"):
        service.create_upload(
            actor_id=actor_id,
            system_id=system_id,
            document_id=replay_document_id,
            document_name="Guide",
            filename="same.md",
            media_type="text/markdown",
            content=BytesIO(content),
            content_length=len(content),
            sha256="b" * 64,
            idempotency_key="operation-switch",
        )


def test_existing_document_upload_stores_object_before_allocating_version_number() -> None:
    events: list[str] = []
    repository = IngestionRepositoryFake(events)
    object_store = ObjectStoreFake(events)
    service = DocumentIngestionService(
        repository=repository,
        object_store=object_store,
        parser_registry=ParserRegistry.default(),
        settings=DocumentProcessingSettings(max_file_bytes=128),
        max_attempts=3,
    )
    actor_id, system_id = uuid4(), uuid4()
    first_content = b"# v1\n"
    first = service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_name="Guide",
        filename="guide.md",
        media_type="text/markdown",
        content=BytesIO(first_content),
        content_length=len(first_content),
        sha256="a" * 64,
        idempotency_key="upload-v1",
    )
    events.clear()
    second_content = b"# v2\n"

    service.create_upload(
        actor_id=actor_id,
        system_id=system_id,
        document_id=first.document.id,
        document_name="Guide",
        filename="guide-v2.md",
        media_type="text/markdown",
        content=BytesIO(second_content),
        content_length=len(second_content),
        sha256="b" * 64,
        idempotency_key="upload-v2",
    )

    assert events == ["object_put", "next_version_no"]


def test_idempotency_key_reuse_with_different_payload_is_rejected() -> None:
    service, _, _ = make_service()
    actor_id, system_id = uuid4(), uuid4()
    first = b"# First\n"
    second = b"# Second\n"
    common = {
        "actor_id": actor_id,
        "system_id": system_id,
        "document_name": "Guide",
        "filename": "guide.md",
        "media_type": "text/markdown",
        "idempotency_key": "upload-001",
    }
    service.create_upload(
        content=BytesIO(first), content_length=len(first), sha256="a" * 64, **common
    )

    with pytest.raises(ConflictError, match="幂等键"):
        service.create_upload(
            content=BytesIO(second), content_length=len(second), sha256="b" * 64, **common
        )


def test_idempotency_key_reuse_is_scoped_and_rejects_changed_payload_within_scope() -> None:
    service, _, _ = make_service()
    actor_id, system_id = uuid4(), uuid4()
    content = b"# Guide\n"
    common = {
        "system_id": system_id,
        "filename": "guide.md",
        "media_type": "text/markdown",
        "content_length": len(content),
        "sha256": "a" * 64,
        "idempotency_key": "upload-001",
    }
    service.create_upload(
        actor_id=actor_id,
        document_name="Guide",
        content=BytesIO(content),
        **common,
    )

    with pytest.raises(ConflictError, match="幂等键"):
        service.create_upload(
            actor_id=actor_id,
            document_name="Renamed guide",
            content=BytesIO(content),
            **common,
        )
    other_actor = service.create_upload(
        actor_id=uuid4(),
        document_name="Guide",
        content=BytesIO(content),
        **common,
    )
    other_system = service.create_upload(
        actor_id=actor_id,
        system_id=uuid4(),
        document_name="Guide",
        filename="guide.md",
        media_type="text/markdown",
        content=BytesIO(content),
        content_length=len(content),
        sha256="a" * 64,
        idempotency_key="upload-001",
    )

    assert other_actor.document.created_by != actor_id
    assert other_system.document.system_id != system_id


def test_upload_rejects_unsupported_empty_and_oversized_files_before_storage() -> None:
    service, _, object_store = make_service()

    with pytest.raises(ValidationError, match="不支持"):
        service.create_upload(
            actor_id=uuid4(),
            system_id=uuid4(),
            document_name="Legacy",
            filename="legacy.doc",
            media_type="application/msword",
            content=BytesIO(b"legacy"),
            content_length=6,
            sha256="a" * 64,
            idempotency_key="unsupported",
        )
    with pytest.raises(ValidationError, match="为空"):
        create_upload(service, idempotency_key="empty", content=b"")
    with pytest.raises(ValidationError, match="上限"):
        create_upload(service, idempotency_key="large", content=b"x" * 129)
    assert object_store.put_calls == 0


def test_upload_rejects_invalid_metadata_and_cleans_object_when_database_write_fails() -> None:
    service, _, object_store = make_service()
    common = {
        "actor_id": uuid4(),
        "system_id": uuid4(),
        "document_name": "Guide",
        "filename": "guide.md",
        "media_type": "text/markdown",
        "content": BytesIO(b"# Guide\n"),
        "content_length": 8,
        "sha256": "a" * 64,
        "idempotency_key": "upload-valid",
    }
    with pytest.raises(ValidationError, match="名称"):
        service.create_upload(**{**common, "document_name": " "})
    with pytest.raises(ValidationError, match="校验值"):
        service.create_upload(**{**common, "content": BytesIO(b"# Guide\n"), "sha256": "bad"})
    with pytest.raises(ValidationError, match="幂等键"):
        service.create_upload(
            **{
                **common,
                "content": BytesIO(b"# Guide\n"),
                "idempotency_key": "bad key",
            }
        )

    failing_store = ObjectStoreFake()
    failing_service = DocumentIngestionService(
        repository=FailingRepositoryFake(),
        object_store=failing_store,
        parser_registry=ParserRegistry.default(),
        settings=DocumentProcessingSettings(max_file_bytes=128),
        max_attempts=3,
    )
    with pytest.raises(RuntimeError, match="database failed"):
        failing_service.create_upload(**{**common, "content": BytesIO(b"# Guide\n")})
    assert failing_store.objects == {}


def test_upload_cleans_object_when_post_persist_action_fails() -> None:
    service, _, object_store = make_service()

    def fail_audit(_: IngestionBundle) -> None:
        raise RuntimeError("audit failed")

    with pytest.raises(RuntimeError, match="audit failed"):
        service.create_upload(
            actor_id=uuid4(),
            system_id=uuid4(),
            document_name="Guide",
            filename="guide.md",
            media_type="text/markdown",
            content=BytesIO(b"# Guide\n"),
            content_length=8,
            sha256="a" * 64,
            idempotency_key="upload-audit-failure",
            on_persisted=fail_audit,
        )

    assert object_store.objects == {}
