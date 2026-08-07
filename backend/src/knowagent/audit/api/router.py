from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from knowagent.audit.api.schemas import AuditLogPage, AuditLogView
from knowagent.audit.application.audit_query_service import AuditLogFilter, AuditQueryService
from knowagent.identity.api.dependencies import AdminContext, DatabaseSession

router = APIRouter()


@router.get("/admin/audit-logs", response_model=AuditLogPage)
def list_audit_logs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    context: AdminContext,
    database: DatabaseSession,
    actor_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    object_type: Annotated[str | None, Query(max_length=64)] = None,
    object_id: Annotated[UUID | None, Query()] = None,
    result: Annotated[str | None, Query(max_length=32)] = None,
    started_at: Annotated[datetime | None, Query()] = None,
    ended_at: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AuditLogPage:
    del context
    filters = AuditLogFilter(
        actor_id=actor_id,
        action=action.strip() if action is not None else None,
        object_type=object_type.strip() if object_type is not None else None,
        object_id=object_id,
        result=result.strip() if result is not None else None,
        started_at=started_at,
        ended_at=ended_at,
    )
    entries, total = AuditQueryService(database).list_audit_logs(
        page=page,
        page_size=page_size,
        filters=filters,
    )
    return AuditLogPage(
        items=[
            AuditLogView(
                id=entry.id,
                actor_id=entry.actor_id,
                action=entry.action,
                object_type=entry.object_type,
                object_id=entry.object_id,
                result=entry.result,
                request_id=entry.request_id,
                context_data=entry.context_data,
                created_at=entry.created_at,
                detail=entry.detail,
            )
            for entry in entries
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
