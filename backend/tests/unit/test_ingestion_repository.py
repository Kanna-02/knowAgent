from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.documents.domain.ingestion import (
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionBundle,
    IngestionJob,
    IngestionStage,
    IngestionStatus,
)
from knowagent.documents.errors import IngestionLeaseLostError
from knowagent.documents.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIngestionCoordinator,
    SqlAlchemyIngestionRepository,
)
from knowagent.identity.infrastructure.sqlalchemy_models import Base

NOW = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)


def make_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def make_bundle() -> IngestionBundle:
    actor_id, document_id, version_id, system_id = uuid4(), uuid4(), uuid4(), uuid4()
    return IngestionBundle(
        document=Document(
            id=document_id,
            system_id=system_id,
            name="Guide",
            created_by=actor_id,
            created_at=NOW,
            updated_at=NOW,
        ),
        version=DocumentVersion(
            id=version_id,
            document_id=document_id,
            system_id=system_id,
            version_no=1,
            object_key="documents/source.md",
            filename="guide.md",
            media_type="text/markdown",
            size_bytes=25,
            sha256="a" * 64,
            status=DocumentVersionStatus.UPLOADED,
            created_by=actor_id,
            created_at=NOW,
            updated_at=NOW,
        ),
        job=IngestionJob.new(
            document_version_id=version_id,
            actor_id=actor_id,
            system_id=system_id,
            idempotency_key="upload-001",
            max_attempts=3,
            now=NOW,
        ),
    )


def test_repository_round_trips_bundle_by_idempotency_key_and_job_id() -> None:
    factory = make_factory()
    bundle = make_bundle()
    with factory.begin() as session:
        created = SqlAlchemyIngestionRepository(session).add(bundle)
        assert created == bundle
    with factory() as session:
        repository = SqlAlchemyIngestionRepository(session)
        assert (
            repository.get_by_idempotency_key(
                "upload-001",
                actor_id=bundle.job.actor_id,
                system_id=bundle.job.system_id,
            )
            == bundle
        )
        assert repository.get_by_job_id(bundle.job.id) == bundle


def test_repository_persists_requested_document_and_updates_logical_document_time() -> None:
    factory = make_factory()
    first = make_bundle()
    later = NOW + timedelta(minutes=5)
    second_version_id = uuid4()
    second = IngestionBundle(
        document=first.document,
        version=replace(
            first.version,
            id=second_version_id,
            version_no=2,
            object_key="documents/source-v2.md",
            filename="guide-v2.md",
            sha256="b" * 64,
            created_at=later,
            updated_at=later,
        ),
        job=IngestionJob.new(
            document_version_id=second_version_id,
            actor_id=first.job.actor_id,
            system_id=first.job.system_id,
            requested_document_id=first.document.id,
            idempotency_key="upload-002",
            max_attempts=3,
            now=later,
        ),
    )
    with factory.begin() as session:
        repository = SqlAlchemyIngestionRepository(session)
        repository.add(first)
        repository.add(second)
    with factory() as session:
        repository = SqlAlchemyIngestionRepository(session)
        stored = repository.get_by_job_id(second.job.id)
        document = repository.get_document(
            system_id=first.document.system_id,
            document_id=first.document.id,
        )

    assert stored is not None and stored.job.requested_document_id == first.document.id
    assert document is not None and document.updated_at == later


def test_coordinator_persists_claim_progress_and_completion_across_sessions() -> None:
    factory = make_factory()
    bundle = make_bundle()
    with factory.begin() as session:
        SqlAlchemyIngestionRepository(session).add(bundle)
    coordinator = SqlAlchemyIngestionCoordinator(factory)

    claimed = coordinator.claim(bundle.job.id, owner="worker-1", now=NOW, lease_seconds=60)
    assert claimed is not None and claimed.job.attempt == 1
    coordinator.advance(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        stage=IngestionStage.PARSING,
        progress=20,
        version_status=DocumentVersionStatus.PARSING,
        now=NOW,
    )
    completed = coordinator.complete(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        manifest_key="documents/chunks-v1.json",
        chunk_count=2,
        parser_name="markdown-it-py",
        parser_version="4.2.0",
        schema_version="1",
        now=NOW,
    )

    assert completed.job.status is IngestionStatus.SUCCEEDED
    assert completed.version.status is DocumentVersionStatus.CHUNKED
    with factory() as session:
        persisted = SqlAlchemyIngestionRepository(session).get_by_job_id(bundle.job.id)
        assert persisted == completed


def test_coordinator_persists_chunking_lease_continuation_and_manifest_across_sessions() -> None:
    factory = make_factory()
    bundle = make_bundle()
    with factory.begin() as session:
        SqlAlchemyIngestionRepository(session).add(bundle)
    coordinator = SqlAlchemyIngestionCoordinator(factory)

    claimed = coordinator.claim(bundle.job.id, owner="worker-1", now=NOW, lease_seconds=60)
    assert claimed is not None
    coordinator.advance(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        stage=IngestionStage.CHUNKING,
        progress=70,
        version_status=DocumentVersionStatus.CHUNKING,
        now=NOW,
    )
    released = coordinator.release_for_continuation(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        now=NOW,
    )
    continued = coordinator.claim_continuation(
        bundle.job.id,
        owner="worker-2",
        now=NOW,
        lease_seconds=60,
    )
    assert continued is not None
    recorded = coordinator.record_chunk_manifest(
        bundle.job.id,
        owner="worker-2",
        attempt=continued.job.attempt,
        manifest_key="documents/chunks-v1.json",
        chunk_count=3,
        parser_name="markdown-it-py",
        parser_version="4.2.0",
        schema_version="chunks-v1",
        now=NOW,
    )

    assert released.job.status is IngestionStatus.QUEUED
    assert released.job.attempt == 1
    assert released.job.progress == 70
    assert released.version.status is DocumentVersionStatus.CHUNKED
    assert continued.job.status is IngestionStatus.RUNNING
    assert continued.job.stage is IngestionStage.CHUNKING
    assert continued.job.attempt == 1
    assert recorded.version.chunk_manifest_key == "documents/chunks-v1.json"
    assert recorded.version.chunk_count == 3
    with factory() as session:
        persisted = SqlAlchemyIngestionRepository(session).get_by_job_id(bundle.job.id)
        assert persisted is not None
        assert persisted.job.stage is IngestionStage.CHUNKING
        assert persisted.job.attempt == 1
        assert persisted.version.chunk_manifest_key == "documents/chunks-v1.json"


def test_coordinator_claims_due_chunking_retry_continuation_across_sessions() -> None:
    factory = make_factory()
    bundle = make_bundle()
    with factory.begin() as session:
        SqlAlchemyIngestionRepository(session).add(bundle)
    coordinator = SqlAlchemyIngestionCoordinator(factory)

    claimed = coordinator.claim(bundle.job.id, owner="worker-1", now=NOW, lease_seconds=60)
    assert claimed is not None
    coordinator.advance(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        stage=IngestionStage.CHUNKING,
        progress=70,
        version_status=DocumentVersionStatus.CHUNKING,
        now=NOW,
    )
    failed = coordinator.fail(
        bundle.job.id,
        owner="worker-1",
        attempt=claimed.job.attempt,
        error_code="EMBEDDING_UNAVAILABLE",
        error_message="temporary failure",
        retryable=True,
        version_status=DocumentVersionStatus.CHUNKED,
        now=NOW,
        retry_base_seconds=10,
    )
    assert failed.job.next_retry_at is not None

    continued = coordinator.claim_continuation(
        bundle.job.id,
        owner="worker-2",
        now=failed.job.next_retry_at,
        lease_seconds=60,
    )

    assert continued is not None
    assert continued.job.status is IngestionStatus.RUNNING
    assert continued.job.stage is IngestionStage.CHUNKING
    assert continued.job.progress == 70
    assert continued.job.attempt == 2
    with factory() as session:
        persisted = SqlAlchemyIngestionRepository(session).get_by_job_id(bundle.job.id)
        assert persisted is not None
        assert persisted.job.attempt == 2
        assert persisted.job.lease_owner == "worker-2"


def test_recovery_requeues_expired_lease_and_limits_dispatch_frequency() -> None:
    factory = make_factory()
    bundle = make_bundle()
    expired = bundle.job.claim(owner="dead-worker", now=NOW, lease_seconds=10)
    bundle = replace(bundle, job=expired)
    with factory.begin() as session:
        SqlAlchemyIngestionRepository(session).add(bundle)
    coordinator = SqlAlchemyIngestionCoordinator(factory)

    recovered = coordinator.recover_and_find_dispatchable(
        now=NOW + timedelta(seconds=11),
        stale_before=NOW - timedelta(minutes=1),
        limit=10,
    )
    coordinator.mark_dispatched(
        bundle.job.id,
        celery_task_id="task-1",
        now=NOW + timedelta(seconds=11),
    )
    not_stale = coordinator.recover_and_find_dispatchable(
        now=NOW + timedelta(seconds=12),
        stale_before=NOW,
        limit=10,
    )
    stale = coordinator.recover_and_find_dispatchable(
        now=NOW + timedelta(minutes=2),
        stale_before=NOW + timedelta(minutes=1),
        limit=10,
    )

    assert recovered == [bundle.job.id]
    assert not_stale == []
    assert stale == [bundle.job.id]
    with factory() as session:
        repository = SqlAlchemyIngestionRepository(session)
        job = repository.get_job(bundle.job.id)
        recovered_bundle = repository.get_by_job_id(bundle.job.id)
        assert job is not None
        assert recovered_bundle is not None
        assert job.status is IngestionStatus.QUEUED
        assert job.error_code == "LEASE_EXPIRED"
        assert job.celery_task_id == "task-1"
        assert recovered_bundle.version.status is DocumentVersionStatus.UPLOADED


def test_stale_worker_cannot_advance_after_job_is_reclaimed() -> None:
    factory = make_factory()
    bundle = make_bundle()
    with factory.begin() as session:
        SqlAlchemyIngestionRepository(session).add(bundle)
    coordinator = SqlAlchemyIngestionCoordinator(factory)
    first = coordinator.claim(bundle.job.id, owner="worker-1", now=NOW, lease_seconds=10)
    assert first is not None
    coordinator.recover_and_find_dispatchable(
        now=NOW + timedelta(seconds=11),
        stale_before=NOW,
        limit=10,
    )
    second = coordinator.claim(
        bundle.job.id,
        owner="worker-2",
        now=NOW + timedelta(seconds=11),
        lease_seconds=60,
    )
    assert second is not None

    with pytest.raises(IngestionLeaseLostError):
        coordinator.complete(
            bundle.job.id,
            owner="worker-1",
            attempt=first.job.attempt,
            manifest_key="documents/stale.json",
            chunk_count=1,
            parser_name="markdown-it-py",
            parser_version="4.2.0",
            schema_version="1",
            now=NOW + timedelta(seconds=12),
        )

    with factory() as session:
        current = SqlAlchemyIngestionRepository(session).get_job(bundle.job.id)
        assert current is not None
        assert current.status is IngestionStatus.RUNNING
        assert current.lease_owner == "worker-2"
        assert current.attempt == second.job.attempt
