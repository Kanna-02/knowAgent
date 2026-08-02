from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from knowagent.identity.api.dependencies import (
    AdminContext,
    AdminCsrfContext,
    AuthServiceDependency,
    CurrentContextDependency,
    DatabaseSession,
    RedisClient,
)
from knowagent.identity.domain.models import AccountRole
from knowagent.identity.infrastructure.redis_session import RedisSessionStore
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink
from knowagent.systems.api.schemas import (
    BusinessSystemPage,
    BusinessSystemView,
    OwnerAssignmentRequest,
    SystemCreateRequest,
    SystemOwnerView,
    SystemUpdateRequest,
)
from knowagent.systems.application.system_service import SystemService
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAccountDirectory,
    SqlAlchemySystemRepository,
)


router = APIRouter()


@router.get("/systems", response_model=list[BusinessSystemView])
def list_systems(
    request: Request,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    redis: RedisClient,
    system_status: Annotated[BusinessSystemStatus | None, Query(alias="status")] = None,
) -> list[BusinessSystemView]:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    if context.account.role is not AccountRole.ADMIN:
        if system_status is BusinessSystemStatus.DISABLED:
            return []
        system_status = BusinessSystemStatus.ACTIVE
    return [
        BusinessSystemView.from_system(item)
        for item in _system_service(request, database, redis).list(
            status=system_status,
            include_owners=context.account.role is AccountRole.ADMIN,
        )
    ]


@router.get("/admin/systems", response_model=BusinessSystemPage)
def list_admin_systems(
    request: Request,
    context: AdminContext,
    database: DatabaseSession,
    redis: RedisClient,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    system_status: Annotated[BusinessSystemStatus | None, Query(alias="status")] = None,
) -> BusinessSystemPage:
    del context
    items, total = _system_service(request, database, redis).list_page(
        page=page,
        page_size=page_size,
        status=system_status,
    )
    return BusinessSystemPage(
        items=[BusinessSystemView.from_system(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/admin/systems",
    response_model=BusinessSystemView,
    status_code=status.HTTP_201_CREATED,
)
def create_system(
    payload: SystemCreateRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> BusinessSystemView:
    created = _system_service(request, database, redis).create(
        actor_id=context.account.id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        request_id=request.state.request_id,
    )
    return BusinessSystemView.from_system(created)


@router.patch("/admin/systems/{system_id}", response_model=BusinessSystemView)
def update_system(
    system_id: UUID,
    payload: SystemUpdateRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> BusinessSystemView:
    updated = _system_service(request, database, redis).update(
        actor_id=context.account.id,
        system_id=system_id,
        name=payload.name,
        description=payload.description,
        description_is_set="description" in payload.model_fields_set,
        status=payload.status,
        request_id=request.state.request_id,
    )
    return BusinessSystemView.from_system(updated)


@router.put(
    "/admin/systems/{system_id}/owners",
    response_model=list[SystemOwnerView],
)
def assign_system_owners(
    system_id: UUID,
    payload: OwnerAssignmentRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> list[SystemOwnerView]:
    owners = _system_service(request, database, redis).assign_owners(
        actor_id=context.account.id,
        system_id=system_id,
        account_ids=payload.account_ids,
        replace_existing=payload.replace_existing,
        request_id=request.state.request_id,
    )
    return [SystemOwnerView.from_owner(owner) for owner in owners]


def _system_service(
    request: Request, database: DatabaseSession, redis: RedisClient
) -> SystemService:
    return SystemService(
        systems=SqlAlchemySystemRepository(database),
        accounts=SqlAlchemyAccountDirectory(database),
        sessions=RedisSessionStore(redis, prefix=request.app.state.settings.redis_prefix),
        audit=SqlAlchemyAuditSink(database),
    )
