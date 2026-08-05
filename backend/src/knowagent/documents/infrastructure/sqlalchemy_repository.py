from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from knowagent.common.errors import ConflictError, ValidationError
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
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
    IngestionJobRecord,
)


class SqlAlchemyIngestionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_idempotency_key(
        self, key: str, *, actor_id: UUID, system_id: UUID
    ) -> IngestionBundle | None:
        job = self._session.scalar(
            select(IngestionJobRecord).where(
                IngestionJobRecord.idempotency_key == key,
                IngestionJobRecord.actor_id == actor_id,
                IngestionJobRecord.system_id == system_id,
            )
        )
        return self._bundle_from_job(job) if job is not None else None

    def get_document(self, *, system_id: UUID, document_id: UUID) -> Document | None:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.system_id == system_id,
            )
        )
        return self._to_document(record) if record is not None else None

    def next_version_no(self, *, system_id: UUID, document_id: UUID) -> int:
        document = self._session.scalar(
            select(DocumentRecord)
            .where(
                DocumentRecord.id == document_id,
                DocumentRecord.system_id == system_id,
            )
            .with_for_update()
        )
        if document is None:
            raise ValidationError("DOCUMENT_NOT_FOUND", "文档不存在")
        current = self._session.scalar(
            select(func.max(DocumentVersionRecord.version_no)).where(
                DocumentVersionRecord.document_id == document_id,
                DocumentVersionRecord.system_id == system_id,
            )
        )
        return int(current or 0) + 1

    def get_by_job_id(self, job_id: UUID) -> IngestionBundle | None:
        job = self._session.get(IngestionJobRecord, job_id)
        return self._bundle_from_job(job) if job is not None else None

    def add(self, bundle: IngestionBundle) -> IngestionBundle:
        existing_document = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == bundle.document.id,
                DocumentRecord.system_id == bundle.document.system_id,
            )
        )
        records = [self._version_record(bundle.version), self._job_record(bundle.job)]
        if existing_document is None:
            records.insert(0, self._document_record(bundle.document))
        else:
            existing_document.updated_at = max(
                _aware(existing_document.updated_at),
                bundle.version.created_at,
            )
        try:
            with self._session.begin_nested():
                self._session.add_all(records)
                self._session.flush()
        except IntegrityError as error:
            existing = self.get_by_idempotency_key(
                bundle.job.idempotency_key,
                actor_id=bundle.job.actor_id,
                system_id=bundle.job.system_id,
            )
            if existing is not None:
                return existing
            raise ConflictError("DOCUMENT_UPLOAD_CONFLICT", "文档上传发生并发冲突") from error
        return bundle

    def get_job(self, job_id: UUID) -> IngestionJob | None:
        record = self._session.get(IngestionJobRecord, job_id)
        return self._to_job(record) if record is not None else None

    def save_job(self, job: IngestionJob) -> IngestionJob:
        record = self._session.get(IngestionJobRecord, job.id)
        if record is None:
            raise ValidationError("INGESTION_JOB_NOT_FOUND", "入库任务不存在")
        self._apply_job(record, job)
        self._session.flush()
        return self._to_job(record)

    def save_version(self, version: DocumentVersion) -> DocumentVersion:
        record = self._session.get(DocumentVersionRecord, version.id)
        if record is None:
            raise ValidationError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
        self._apply_version(record, version)
        self._session.flush()
        return self._to_version(record)

    def dispatchable_job_ids(
        self, *, now: datetime, stale_before: datetime, limit: int
    ) -> list[UUID]:
        dispatch_stale = or_(
            IngestionJobRecord.last_dispatched_at.is_(None),
            IngestionJobRecord.last_dispatched_at < stale_before,
        )
        statement = (
            select(IngestionJobRecord.id)
            .where(
                or_(
                    and_(
                        IngestionJobRecord.status == IngestionStatus.QUEUED,
                        dispatch_stale,
                    ),
                    and_(
                        IngestionJobRecord.status == IngestionStatus.RETRY_SCHEDULED,
                        IngestionJobRecord.next_retry_at <= now,
                        dispatch_stale,
                    ),
                )
            )
            .order_by(IngestionJobRecord.created_at, IngestionJobRecord.id)
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def _bundle_from_job(self, job: IngestionJobRecord) -> IngestionBundle:
        version = self._session.get(DocumentVersionRecord, job.document_version_id)
        if version is None:
            raise RuntimeError("ingestion job references a missing document version")
        document = self._session.get(DocumentRecord, version.document_id)
        if document is None:
            raise RuntimeError("document version references a missing document")
        return IngestionBundle(
            document=self._to_document(document),
            version=self._to_version(version),
            job=self._to_job(job),
        )

    @staticmethod
    def _document_record(document: Document) -> DocumentRecord:
        return DocumentRecord(
            id=document.id,
            system_id=document.system_id,
            name=document.name,
            current_published_version_id=document.current_published_version_id,
            created_by=document.created_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    def _version_record(version: DocumentVersion) -> DocumentVersionRecord:
        return DocumentVersionRecord(
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

    @staticmethod
    def _job_record(job: IngestionJob) -> IngestionJobRecord:
        return IngestionJobRecord(
            id=job.id,
            document_version_id=job.document_version_id,
            actor_id=job.actor_id,
            system_id=job.system_id,
            requested_document_id=job.requested_document_id,
            idempotency_key=job.idempotency_key,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            lease_owner=job.lease_owner,
            lease_expires_at=job.lease_expires_at,
            next_retry_at=job.next_retry_at,
            error_code=job.error_code,
            error_message=job.error_message,
            celery_task_id=job.celery_task_id,
            last_dispatched_at=job.last_dispatched_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _apply_job(record: IngestionJobRecord, job: IngestionJob) -> None:
        for name in (
            "status",
            "stage",
            "progress",
            "attempt",
            "max_attempts",
            "lease_owner",
            "lease_expires_at",
            "next_retry_at",
            "error_code",
            "error_message",
            "celery_task_id",
            "last_dispatched_at",
            "started_at",
            "completed_at",
            "updated_at",
        ):
            setattr(record, name, getattr(job, name))

    @staticmethod
    def _apply_version(record: DocumentVersionRecord, version: DocumentVersion) -> None:
        for name in (
            "status",
            "publish_status",
            "published_at",
            "retired_at",
            "chunk_manifest_key",
            "chunk_count",
            "parser_name",
            "parser_version",
            "schema_version",
            "updated_at",
        ):
            setattr(record, name, getattr(version, name))

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
            created_by=record.created_by,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
            chunk_manifest_key=record.chunk_manifest_key,
            chunk_count=record.chunk_count,
            parser_name=record.parser_name,
            parser_version=record.parser_version,
            schema_version=record.schema_version,
        )

    @staticmethod
    def _to_job(record: IngestionJobRecord) -> IngestionJob:
        return IngestionJob(
            id=record.id,
            document_version_id=record.document_version_id,
            actor_id=record.actor_id,
            system_id=record.system_id,
            requested_document_id=record.requested_document_id,
            idempotency_key=record.idempotency_key,
            status=record.status,
            stage=record.stage,
            progress=record.progress,
            attempt=record.attempt,
            max_attempts=record.max_attempts,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
            lease_owner=record.lease_owner,
            lease_expires_at=_aware_or_none(record.lease_expires_at),
            next_retry_at=_aware_or_none(record.next_retry_at),
            error_code=record.error_code,
            error_message=record.error_message,
            celery_task_id=record.celery_task_id,
            last_dispatched_at=_aware_or_none(record.last_dispatched_at),
            started_at=_aware_or_none(record.started_at),
            completed_at=_aware_or_none(record.completed_at),
        )


class SqlAlchemyIngestionCoordinator:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def claim(
        self, job_id: UUID, *, owner: str, now: datetime, lease_seconds: int
    ) -> IngestionBundle | None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(IngestionJobRecord)
                .where(IngestionJobRecord.id == job_id)
                .with_for_update(skip_locked=True)
            )
            if record is None:
                return None
            repository = SqlAlchemyIngestionRepository(session)
            job = repository._to_job(record)  # pylint: disable=protected-access
            try:
                claimed = job.claim(owner=owner, now=now, lease_seconds=lease_seconds)
            except ValueError:
                return None
            repository.save_job(claimed)
            return repository.get_by_job_id(job_id)

    def advance(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        stage: IngestionStage,
        progress: int,
        version_status: DocumentVersionStatus,
        now: datetime,
    ) -> IngestionBundle:
        with self._session_factory.begin() as session:
            repository, bundle = self._locked_owned_bundle(
                session,
                job_id,
                owner=owner,
                attempt=attempt,
                now=now,
            )
            repository.save_job(bundle.job.advance(stage, progress=progress, now=now))
            repository.save_version(replace(bundle.version, status=version_status, updated_at=now))
            return self._required_bundle(repository, job_id)

    def complete(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        manifest_key: str,
        chunk_count: int,
        parser_name: str,
        parser_version: str,
        schema_version: str,
        now: datetime,
        version_status: DocumentVersionStatus = DocumentVersionStatus.CHUNKED,
    ) -> IngestionBundle:
        with self._session_factory.begin() as session:
            repository, bundle = self._locked_owned_bundle(
                session,
                job_id,
                owner=owner,
                attempt=attempt,
                now=now,
            )
            repository.save_job(bundle.job.complete(now=now))
            repository.save_version(
                replace(
                    bundle.version,
                    status=version_status,
                    chunk_manifest_key=manifest_key,
                    chunk_count=chunk_count,
                    parser_name=parser_name,
                    parser_version=parser_version,
                    schema_version=schema_version,
                    updated_at=now,
                )
            )
            return self._required_bundle(repository, job_id)

    def fail(  # pylint: disable=too-many-arguments
        self,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        error_code: str,
        error_message: str,
        retryable: bool,
        version_status: DocumentVersionStatus,
        now: datetime,
        retry_base_seconds: int,
    ) -> IngestionBundle:
        with self._session_factory.begin() as session:
            repository, bundle = self._locked_owned_bundle(
                session,
                job_id,
                owner=owner,
                attempt=attempt,
                now=now,
            )
            failed = bundle.job.fail(
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                now=now,
                retry_base_seconds=retry_base_seconds,
            )
            repository.save_job(failed)
            repository.save_version(
                replace(
                    bundle.version,
                    status=(
                        DocumentVersionStatus.UPLOADED
                        if failed.status is IngestionStatus.RETRY_SCHEDULED
                        else version_status
                    ),
                    updated_at=now,
                )
            )
            return self._required_bundle(repository, job_id)

    def recover_and_find_dispatchable(
        self, *, now: datetime, stale_before: datetime, limit: int
    ) -> list[UUID]:
        with self._session_factory.begin() as session:
            expired = list(
                session.scalars(
                    select(IngestionJobRecord)
                    .where(
                        IngestionJobRecord.status == IngestionStatus.RUNNING,
                        IngestionJobRecord.lease_expires_at <= now,
                    )
                    .order_by(IngestionJobRecord.lease_expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).all()
            )
            repository = SqlAlchemyIngestionRepository(session)
            for record in expired:
                recovered = repository._to_job(  # pylint: disable=protected-access
                    record
                ).recover_expired(now=now)
                repository.save_job(recovered)
                bundle = self._required_bundle(repository, recovered.id)
                repository.save_version(
                    replace(
                        bundle.version,
                        status=(
                            DocumentVersionStatus.FAILED
                            if recovered.status is IngestionStatus.FAILED
                            else DocumentVersionStatus.UPLOADED
                        ),
                        updated_at=now,
                    )
                )
            return repository.dispatchable_job_ids(now=now, stale_before=stale_before, limit=limit)

    def mark_dispatched(self, job_id: UUID, *, celery_task_id: str, now: datetime) -> None:
        with self._session_factory.begin() as session:
            repository, bundle = self._locked_bundle(session, job_id)
            repository.save_job(
                replace(
                    bundle.job,
                    celery_task_id=celery_task_id,
                    last_dispatched_at=now,
                    updated_at=now,
                )
            )

    def manual_retry(self, job_id: UUID, *, now: datetime) -> IngestionBundle:
        with self._session_factory.begin() as session:
            repository, bundle = self._locked_bundle(session, job_id)
            try:
                retried = bundle.job.manual_retry(now=now)
            except ValueError as error:
                raise ConflictError(
                    "INGESTION_JOB_NOT_RETRYABLE",
                    "只有失败的入库任务可以人工重试",
                ) from error
            repository.save_job(retried)
            repository.save_version(
                replace(bundle.version, status=DocumentVersionStatus.UPLOADED, updated_at=now)
            )
            return self._required_bundle(repository, job_id)

    @classmethod
    def _locked_owned_bundle(
        cls,
        session: Session,
        job_id: UUID,
        *,
        owner: str,
        attempt: int,
        now: datetime,
    ) -> tuple[SqlAlchemyIngestionRepository, IngestionBundle]:
        repository, bundle = cls._locked_bundle(session, job_id)
        job = bundle.job
        if (
            job.status is not IngestionStatus.RUNNING
            or job.lease_owner != owner
            or job.attempt != attempt
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            raise IngestionLeaseLostError(f"ingestion lease lost for job {job_id}")
        return repository, bundle

    @staticmethod
    def _locked_bundle(
        session: Session, job_id: UUID
    ) -> tuple[SqlAlchemyIngestionRepository, IngestionBundle]:
        record = session.scalar(
            select(IngestionJobRecord).where(IngestionJobRecord.id == job_id).with_for_update()
        )
        if record is None:
            raise ValidationError("INGESTION_JOB_NOT_FOUND", "入库任务不存在")
        repository = SqlAlchemyIngestionRepository(session)
        return repository, repository._bundle_from_job(record)  # pylint: disable=protected-access

    @staticmethod
    def _required_bundle(
        repository: SqlAlchemyIngestionRepository, job_id: UUID
    ) -> IngestionBundle:
        bundle = repository.get_by_job_id(job_id)
        if bundle is None:
            raise RuntimeError("ingestion bundle disappeared during transaction")
        return bundle


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _aware_or_none(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None
