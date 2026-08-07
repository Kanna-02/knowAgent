from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.audit.domain.models import AuditLogEntry
from knowagent.identity.infrastructure.sqlalchemy_models import AuditLogRecord


@dataclass(frozen=True, slots=True)
class AuditLogFilter:
    """Admin-facing filter for audit-log queries.

    All fields are optional; an unset field means 'no constraint'. The
    ``started_at``/``ended_at`` window is inclusive on both ends. ``action``
    supports exact match only; callers pass the fully-qualified action string
    (e.g. ``'conversation.create'``).
    """

    actor_id: UUID | None = None
    action: str | None = None
    object_type: str | None = None
    object_id: UUID | None = None
    result: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuditQueryService:  # pylint: disable=too-few-public-methods,not-callable
    """Read-side audit-log querying scoped for the admin audit-logs API.

    The audit table is global (not system-scoped) because audit covers
    authentication and account-management actions that are not tied to a
    business system. Access control is enforced at the API layer: only
    ``ADMIN`` may call this service.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_audit_logs(
        self,
        *,
        page: int,
        page_size: int,
        filters: AuditLogFilter | None = None,
    ) -> tuple[list[AuditLogEntry], int]:
        if page <= 0 or page_size <= 0:
            raise ValueError("audit pagination parameters must be positive")
        conditions = []
        if filters is not None:
            if filters.actor_id is not None:
                conditions.append(AuditLogRecord.actor_id == filters.actor_id)
            if filters.action is not None and filters.action.strip():
                conditions.append(AuditLogRecord.action == filters.action.strip())
            if filters.object_type is not None and filters.object_type.strip():
                conditions.append(AuditLogRecord.object_type == filters.object_type.strip())
            if filters.object_id is not None:
                conditions.append(AuditLogRecord.object_id == filters.object_id)
            if filters.result is not None and filters.result.strip():
                conditions.append(AuditLogRecord.result == filters.result.strip())
            if filters.started_at is not None:
                conditions.append(AuditLogRecord.created_at >= _aware(filters.started_at))
            if filters.ended_at is not None:
                conditions.append(AuditLogRecord.created_at <= _aware(filters.ended_at))
        count = self._session.scalar(
            select(func.count()).select_from(AuditLogRecord).where(*conditions)
        )
        query = (
            select(AuditLogRecord)
            .where(*conditions)
            .order_by(AuditLogRecord.created_at.desc(), AuditLogRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        records = self._session.execute(query).scalars().all()
        return [self._to_entry(record) for record in records], int(count or 0)

    @staticmethod
    def _to_entry(record: AuditLogRecord) -> AuditLogEntry:
        return AuditLogEntry(
            id=record.id,
            actor_id=record.actor_id,
            action=record.action,
            object_type=record.object_type,
            object_id=record.object_id,
            result=record.result,
            request_id=record.request_id,
            context_data=record.context_data,
            created_at=_aware(record.created_at),
            detail=record.detail,
        )
