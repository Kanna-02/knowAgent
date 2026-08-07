from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select

from knowagent.common.errors import NotFoundError
from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.api.lifecycle_schemas import (
    DocumentPage,
    DocumentVersionPage,
    DocumentVersionView,
    DocumentView,
    PublishVersionResponse,
    RetireVersionResponse,
)
from knowagent.documents.infrastructure.sqlalchemy_models import (
    DocumentRecord,
    DocumentVersionRecord,
)
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
from knowagent.knowledge.infrastructure.sqlalchemy_repository import (
    SqlAlchemyKnowledgeRepository,
)

# SQLAlchemy dynamic namespaces trigger false positives on func.count().
# pylint: disable=not-callable


router = APIRouter()

MANAGEMENT_ROLES = {AccountRole.SYSTEM_OWNER, AccountRole.ADMIN}


@router.get("/systems/{system_id}/documents", response_model=DocumentPage)
def list_documents(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentPage:
    auth.authorize(context.account, allowed_roles=MANAGEMENT_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    conditions = [DocumentRecord.system_id == system_id]
    total = database.scalar(select(func.count()).select_from(DocumentRecord).where(*conditions))
    records = database.scalars(
        select(DocumentRecord)
        .where(*conditions)
        .order_by(DocumentRecord.updated_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return DocumentPage(
        items=[_to_document_view(record) for record in records],
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


def _to_document_view(record: DocumentRecord) -> DocumentView:
    return DocumentView(
        id=record.id,
        system_id=record.system_id,
        name=record.name,
        current_published_version_id=record.current_published_version_id,
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
