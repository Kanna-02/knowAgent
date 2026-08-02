from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Header,
    Request,
    UploadFile,
    status,
)

from knowagent.common.errors import AuthorizationError, KnowAgentError, NotFoundError
from knowagent.documents.api.schemas import IngestionJobView
from knowagent.documents.application.ingestion_service import DocumentIngestionService
from knowagent.documents.domain.ingestion import IngestionBundle, IngestionStatus
from knowagent.documents.infrastructure.parsers import ParserLimits
from knowagent.documents.infrastructure.parsers.registry import ParserRegistry
from knowagent.documents.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIngestionCoordinator,
    SqlAlchemyIngestionRepository,
)
from knowagent.documents.ports import ObjectStore
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
)
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink
from knowagent.platform.object_store import ObjectStoreError, S3ObjectStore
from knowagent.systems.domain.models import SystemRole, SystemRoleAssignment
from knowagent.systems.infrastructure.sqlalchemy_repository import SqlAlchemySystemRepository

LOGGER = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/systems/{system_id}/documents",
    response_model=IngestionJobView,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    system_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    document_name: Annotated[str | None, Form(max_length=255)] = None,
) -> IngestionJobView:
    _require_system_access(
        system_id=system_id,
        account=context.account,
        auth=auth,
        database=database,
    )
    filename = file.filename or ""
    media_type = file.content_type or "application/octet-stream"
    content_length, sha256 = _measure_upload(
        file, request.app.state.settings.document_processing.max_file_bytes
    )
    service = DocumentIngestionService(
        repository=SqlAlchemyIngestionRepository(database),
        object_store=_object_store(request),
        parser_registry=ParserRegistry.default(
            ParserLimits.from_settings(request.app.state.settings.document_processing)
        ),
        settings=request.app.state.settings.document_processing,
        max_attempts=request.app.state.settings.ingestion.max_attempts,
    )
    audit = SqlAlchemyAuditSink(database)

    def record_upload(persisted: IngestionBundle) -> None:
        audit.record(
            "document.upload",
            "success",
            actor_id=context.account.id,
            object_type="document_version",
            object_id=persisted.version.id,
            request_id=request.state.request_id,
            metadata={"system_id": str(system_id), "job_id": str(persisted.job.id)},
        )

    try:
        bundle = service.create_upload(
            actor_id=context.account.id,
            system_id=system_id,
            document_name=document_name or filename,
            filename=filename,
            media_type=media_type,
            content=file.file,
            content_length=content_length,
            sha256=sha256,
            idempotency_key=idempotency_key,
            on_persisted=record_upload,
        )
    except ObjectStoreError as error:
        raise KnowAgentError(
            "OBJECT_STORE_UNAVAILABLE" if error.retryable else "OBJECT_STORE_REQUEST_FAILED",
            "对象存储暂时不可用" if error.retryable else "对象存储请求失败",
            status_code=503 if error.retryable else 502,
        ) from error
    if bundle.job.status is IngestionStatus.QUEUED and bundle.job.last_dispatched_at is None:
        background_tasks.add_task(_dispatch_job, request.app, bundle.job.id)
    return IngestionJobView.from_bundle(bundle)


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobView)
def get_ingestion_job(
    job_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> IngestionJobView:
    bundle = _bundle_or_404(SqlAlchemyIngestionRepository(database), job_id)
    _require_system_access(
        system_id=bundle.document.system_id,
        account=context.account,
        auth=auth,
        database=database,
    )
    return IngestionJobView.from_bundle(bundle)


@router.post(
    "/ingestion-jobs/{job_id}/retry",
    response_model=IngestionJobView,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_ingestion_job(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    job_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> IngestionJobView:
    current = _bundle_or_404(SqlAlchemyIngestionRepository(database), job_id)
    _require_system_access(
        system_id=current.document.system_id,
        account=context.account,
        auth=auth,
        database=database,
    )
    coordinator: SqlAlchemyIngestionCoordinator = request.app.state.ingestion_coordinator
    retried = coordinator.manual_retry(job_id, now=datetime.now(UTC))
    SqlAlchemyAuditSink(database).record(
        "document.ingestion.retry",
        "success",
        actor_id=context.account.id,
        object_type="ingestion_job",
        object_id=job_id,
        request_id=request.state.request_id,
        metadata={"system_id": str(current.document.system_id)},
    )
    background_tasks.add_task(_dispatch_job, request.app, job_id)
    return IngestionJobView.from_bundle(retried)


def _require_system_access(
    *,
    system_id: UUID,
    account: Account,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> None:
    auth.authorize(
        account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    systems = SqlAlchemySystemRepository(database)
    if systems.get_by_id(system_id) is None:
        raise NotFoundError("SYSTEM_NOT_FOUND", "业务系统不存在")
    if account.role is AccountRole.ADMIN:
        return
    roles: list[SystemRoleAssignment] = systems.list_system_roles(account.id)
    if not any(
        assignment.system_id == system_id and assignment.role is SystemRole.SYSTEM_OWNER
        for assignment in roles
    ):
        raise AuthorizationError("SYSTEM_ACCESS_DENIED", "没有该业务系统的管理权限")


def _measure_upload(file: UploadFile, max_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    file.file.seek(0)
    while chunk := file.file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            file.file.seek(0)
            raise KnowAgentError(
                "DOCUMENT_TOO_LARGE",
                "上传文件超过大小上限",
                status_code=413,
            )
        digest.update(chunk)
    file.file.seek(0)
    return total, digest.hexdigest()


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


def _bundle_or_404(repository: SqlAlchemyIngestionRepository, job_id: UUID) -> IngestionBundle:
    bundle = repository.get_by_job_id(job_id)
    if bundle is None:
        raise NotFoundError("INGESTION_JOB_NOT_FOUND", "入库任务不存在")
    return bundle


def _dispatch_job(application: FastAPI, job_id: UUID) -> None:
    app_state = application.state
    try:
        task_id = app_state.ingestion_dispatcher.enqueue(job_id)
        app_state.ingestion_coordinator.mark_dispatched(
            job_id, celery_task_id=task_id, now=datetime.now(UTC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        LOGGER.exception("ingestion dispatch failed", extra={"job_id": str(job_id)})
