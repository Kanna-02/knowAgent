from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, aliased

from knowagent.common.errors import ConflictError, KnowAgentError, NotFoundError
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.api.lifecycle_schemas import (
    DocumentPage,
    DocumentVersionPage,
    DocumentVersionView,
    DocumentView,
    PublishVersionResponse,
    RetireVersionResponse,
)
from knowagent.documents.domain.ingestion import DocumentVersionStatus, IngestionStatus
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
    IngestionJobRecord,
)
from knowagent.documents.ports import ObjectStore
from knowagent.identity.api.access import require_system_access
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
)
from knowagent.identity.domain.models import AccountRole
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink
from knowagent.knowledge.application.publication import KnowledgePublicationService
from knowagent.knowledge.infrastructure.sqlalchemy_models import (
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
)
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)
from knowagent.platform.object_store import ObjectStoreError, S3ObjectStore

# SQLAlchemy dynamic namespaces trigger false positives on func.count().
# pylint: disable=not-callable


LOGGER = logging.getLogger(__name__)
router = APIRouter()

MANAGEMENT_ROLES = {AccountRole.SYSTEM_OWNER, AccountRole.ADMIN}
ACTIVE_INGESTION_STATUSES = (
    IngestionStatus.QUEUED,
    IngestionStatus.RUNNING,
    IngestionStatus.RETRY_SCHEDULED,
)


@router.get("/systems/{system_id}/documents", response_model=DocumentPage)
def list_documents(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=255)] = None,
    latest_status: Annotated[DocumentVersionStatus | None, Query(alias="latest_status")] = None,
    published: Annotated[bool | None, Query()] = None,
) -> DocumentPage:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    conditions = [DocumentRecord.system_id == system_id]
    if search and search.strip():
        conditions.append(DocumentRecord.name.contains(search.strip(), autoescape=True))
    if published is True:
        conditions.append(DocumentRecord.current_published_version_id.is_not(None))
    elif published is False:
        conditions.append(DocumentRecord.current_published_version_id.is_(None))

    version_summary = (
        select(
            DocumentVersionRecord.document_id.label("document_id"),
            func.count().label("version_count"),
            func.max(DocumentVersionRecord.version_no).label("latest_version_no"),
        )
        .group_by(DocumentVersionRecord.document_id)
        .subquery()
    )
    latest_version = aliased(DocumentVersionRecord)
    current_version = aliased(DocumentVersionRecord)
    if latest_status is not None:
        conditions.append(latest_version.status == latest_status)
    total = database.scalar(
        select(func.count())
        .select_from(DocumentRecord)
        .outerjoin(
            version_summary,
            version_summary.c.document_id == DocumentRecord.id,
        )
        .outerjoin(
            latest_version,
            (latest_version.document_id == DocumentRecord.id)
            & (latest_version.version_no == version_summary.c.latest_version_no),
        )
        .where(*conditions)
    )
    rows = database.execute(
        select(
            DocumentRecord,
            version_summary.c.version_count,
            version_summary.c.latest_version_no,
            latest_version.status,
            current_version.version_no,
        )
        .outerjoin(
            version_summary,
            version_summary.c.document_id == DocumentRecord.id,
        )
        .outerjoin(
            latest_version,
            (latest_version.document_id == DocumentRecord.id)
            & (latest_version.version_no == version_summary.c.latest_version_no),
        )
        .outerjoin(
            current_version,
            current_version.id == DocumentRecord.current_published_version_id,
        )
        .where(*conditions)
        .order_by(DocumentRecord.updated_at.desc(), DocumentRecord.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return DocumentPage(
        items=[
            _to_document_view(
                record,
                version_count=int(version_count or 0),
                latest_version_no=latest_version_no,
                latest_version_status=latest_version_status,
                current_published_version_no=current_published_version_no,
            )
            for (
                record,
                version_count,
                latest_version_no,
                latest_version_status,
                current_published_version_no,
            ) in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total or 0),
    )


@router.get(
    "/systems/{system_id}/documents/{document_id}/versions",
    response_model=DocumentVersionPage,
)
def list_document_versions(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    document_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=255)] = None,
    statuses: Annotated[
        list[DocumentVersionStatus] | None,
        Query(alias="status"),
    ] = None,
    publish_statuses: Annotated[
        list[PublicationStatus] | None,
        Query(alias="publish_status"),
    ] = None,
) -> DocumentVersionPage:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    document = database.scalar(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.system_id == system_id,
        )
    )
    if document is None:
        raise NotFoundError("DOCUMENT_NOT_FOUND", "文档不存在")
    conditions = [DocumentVersionRecord.document_id == document_id]
    if search and search.strip():
        conditions.append(DocumentVersionRecord.filename.contains(search.strip(), autoescape=True))
    if statuses:
        conditions.append(DocumentVersionRecord.status.in_(statuses))
    if publish_statuses:
        conditions.append(DocumentVersionRecord.publish_status.in_(publish_statuses))
    total = database.scalar(
        select(func.count()).select_from(DocumentVersionRecord).where(*conditions)
    )
    records = database.scalars(
        select(DocumentVersionRecord)
        .where(*conditions)
        .order_by(DocumentVersionRecord.version_no.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return DocumentVersionPage(
        items=[_to_version_view(record) for record in records],
        page=page,
        page_size=page_size,
        total=int(total or 0),
    )


@router.delete(
    "/systems/{system_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    document_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> None:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    document = database.scalar(
        select(DocumentRecord)
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.system_id == system_id,
        )
        .with_for_update()
    )
    if document is None:
        raise NotFoundError("DOCUMENT_NOT_FOUND", "文档不存在")
    versions = database.scalars(
        select(DocumentVersionRecord)
        .where(
            DocumentVersionRecord.document_id == document_id,
            DocumentVersionRecord.system_id == system_id,
        )
        .with_for_update()
    ).all()
    version_ids = [version.id for version in versions]
    _raise_if_ingesting(database=database, version_ids=version_ids)
    object_keys = _collect_object_keys(versions)
    _delete_version_rows(
        database=database,
        system_id=system_id,
        document_id=document_id,
        version_ids=version_ids,
    )
    database.execute(
        delete(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.system_id == system_id,
        )
    )
    SqlAlchemyAuditSink(database).record(
        "document.delete",
        "success",
        actor_id=context.account.id,
        object_type="document",
        object_id=document_id,
        request_id=request.state.request_id,
        metadata={"system_id": str(system_id), "version_count": len(version_ids)},
    )
    database.commit()
    _delete_objects_best_effort(_object_store(request), object_keys)


@router.delete(
    "/systems/{system_id}/documents/{document_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document_version(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    document_id: UUID,
    version_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> None:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    document = database.scalar(
        select(DocumentRecord)
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.system_id == system_id,
        )
        .with_for_update()
    )
    if document is None:
        raise NotFoundError("DOCUMENT_NOT_FOUND", "文档不存在")
    version = database.scalar(
        select(DocumentVersionRecord)
        .where(
            DocumentVersionRecord.id == version_id,
            DocumentVersionRecord.document_id == document_id,
            DocumentVersionRecord.system_id == system_id,
        )
        .with_for_update()
    )
    if version is None:
        raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
    _raise_if_ingesting(database=database, version_ids=[version.id])
    now = datetime.now(UTC)
    database.execute(
        update(DocumentRecord)
        .where(
            DocumentRecord.id == document_id,
            DocumentRecord.system_id == system_id,
            DocumentRecord.current_published_version_id == version.id,
        )
        .values(current_published_version_id=None, updated_at=now)
    )
    object_keys = _collect_object_keys([version])
    _delete_version_rows(
        database=database,
        system_id=system_id,
        document_id=document_id,
        version_ids=[version.id],
    )
    SqlAlchemyAuditSink(database).record(
        "document_version.delete",
        "success",
        actor_id=context.account.id,
        object_type="document_version",
        object_id=version_id,
        request_id=request.state.request_id,
        metadata={
            "system_id": str(system_id),
            "document_id": str(document_id),
            "version_no": version.version_no,
        },
    )
    database.commit()
    _delete_objects_best_effort(_object_store(request), object_keys)


@router.post(
    "/systems/{system_id}/documents/{document_id}/versions/{version_id}/publish",
    response_model=PublishVersionResponse,
    status_code=status.HTTP_200_OK,
)
def publish_document_version(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    document_id: UUID,
    version_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> PublishVersionResponse:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    repository = SqlAlchemyKnowledgeRepository(database)
    version = repository.get_version(system_id=system_id, document_version_id=version_id)
    if version is None or version.document_id != document_id:
        raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
    session_factory = request.app.state.session_factory
    service = KnowledgePublicationService(session_factory)
    now = datetime.now(UTC)
    service.publish(
        system_id=system_id,
        document_version_id=version_id,
        now=now,
    )
    SqlAlchemyAuditSink(database).record(
        "document.publish",
        "success",
        actor_id=context.account.id,
        object_type="document_version",
        object_id=version_id,
        request_id=request.state.request_id,
        metadata={"system_id": str(system_id), "document_id": str(document_id)},
    )
    return PublishVersionResponse(
        document_id=document_id,
        version_id=version_id,
        system_id=system_id,
        publish_status=PublicationStatus.PUBLISHED,
        published_at=now,
    )


@router.post(
    "/systems/{system_id}/documents/{document_id}/versions/{version_id}/retire",
    response_model=RetireVersionResponse,
    status_code=status.HTTP_200_OK,
)
def retire_document_version(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    document_id: UUID,
    version_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> RetireVersionResponse:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    repository = SqlAlchemyKnowledgeRepository(database)
    version = repository.get_version(system_id=system_id, document_version_id=version_id)
    if version is None or version.document_id != document_id:
        raise NotFoundError("DOCUMENT_VERSION_NOT_FOUND", "文档版本不存在")
    session_factory = request.app.state.session_factory
    service = KnowledgePublicationService(session_factory)
    now = datetime.now(UTC)
    service.retire(
        system_id=system_id,
        document_version_id=version_id,
        now=now,
    )
    SqlAlchemyAuditSink(database).record(
        "document.retire",
        "success",
        actor_id=context.account.id,
        object_type="document_version",
        object_id=version_id,
        request_id=request.state.request_id,
        metadata={"system_id": str(system_id), "document_id": str(document_id)},
    )
    return RetireVersionResponse(
        document_id=document_id,
        version_id=version_id,
        system_id=system_id,
        publish_status=PublicationStatus.RETIRED,
        retired_at=now,
    )


def _raise_if_ingesting(*, database: Session, version_ids: list[UUID]) -> None:
    if not version_ids:
        return
    active = database.scalar(
        select(func.count())
        .select_from(IngestionJobRecord)
        .where(
            IngestionJobRecord.document_version_id.in_(version_ids),
            IngestionJobRecord.status.in_(list(ACTIVE_INGESTION_STATUSES)),
        )
    )
    if active:
        raise ConflictError(
            "DOCUMENT_DELETE_BUSY",
            "文档仍有导入任务正在处理，请等待任务结束后再删除",
        )


def _collect_object_keys(versions: Sequence[DocumentVersionRecord]) -> list[str]:
    keys: list[str] = []
    for version in versions:
        if version.object_key:
            keys.append(version.object_key)
        if version.chunk_manifest_key:
            keys.append(version.chunk_manifest_key)
    return keys


def _delete_version_rows(
    *,
    database: Session,
    system_id: UUID,
    document_id: UUID,
    version_ids: list[UUID],
) -> None:
    if not version_ids:
        return
    source_ids = select(KnowledgeSourceRecord.id).where(
        KnowledgeSourceRecord.system_id == system_id,
        KnowledgeSourceRecord.document_version_id.in_(version_ids),
    )
    database.execute(
        delete(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.system_id == system_id,
            KnowledgeChunkRecord.source_id.in_(source_ids),
        )
    )
    database.execute(
        delete(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.system_id == system_id,
            KnowledgeSourceRecord.document_version_id.in_(version_ids),
        )
    )
    database.execute(
        delete(IngestionJobRecord).where(
            IngestionJobRecord.system_id == system_id,
            IngestionJobRecord.document_version_id.in_(version_ids),
        )
    )
    database.execute(
        delete(DocumentVersionRecord).where(
            DocumentVersionRecord.document_id == document_id,
            DocumentVersionRecord.system_id == system_id,
            DocumentVersionRecord.id.in_(version_ids),
        )
    )


def _object_store(request: Request) -> ObjectStore:
    existing: ObjectStore | None = request.app.state.object_store
    if existing is not None:
        return existing
    settings = request.app.state.settings.object_storage
    if not settings.configured:
        raise KnowAgentError(
            "OBJECT_STORE_NOT_CONFIGURED",
            "对象存储尚未配置",
            status_code=503,
        )
    created = S3ObjectStore.from_settings(settings)
    request.app.state.object_store = created
    return created


def _delete_objects_best_effort(store: ObjectStore, keys: list[str]) -> None:
    for key in keys:
        try:
            store.delete(key=key)
        except ObjectStoreError as error:
            LOGGER.exception(
                "document object cleanup failed",
                extra={"object_key": key, "retryable": error.retryable},
            )
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.exception("document object cleanup failed", extra={"object_key": key})


def _to_document_view(
    record: DocumentRecord,
    *,
    current_published_version_no: int | None,
    latest_version_no: int | None,
    latest_version_status: DocumentVersionStatus | None,
    version_count: int,
) -> DocumentView:
    return DocumentView(
        id=record.id,
        system_id=record.system_id,
        name=record.name,
        current_published_version_id=record.current_published_version_id,
        current_published_version_no=current_published_version_no,
        latest_version_no=latest_version_no,
        latest_version_status=latest_version_status,
        version_count=version_count,
        created_at=_aware(record.created_at),
        updated_at=_aware(record.updated_at),
    )


def _to_version_view(record: DocumentVersionRecord) -> DocumentVersionView:
    return DocumentVersionView(
        id=record.id,
        document_id=record.document_id,
        system_id=record.system_id,
        version_no=record.version_no,
        filename=record.filename,
        media_type=record.media_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        status=record.status,
        publish_status=record.publish_status,
        chunk_count=record.chunk_count,
        parser_name=record.parser_name,
        parser_version=record.parser_version,
        published_at=_aware_or_none(record.published_at),
        retired_at=_aware_or_none(record.retired_at),
        created_at=_aware(record.created_at),
        updated_at=_aware(record.updated_at),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _aware_or_none(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None
