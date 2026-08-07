from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuditLogEntry:  # pylint: disable=too-many-instance-attributes
    """A single audit log entry for read-side queries.

    The write side lives in ``identity.infrastructure.sqlalchemy_repository``
    (:class:`SqlAlchemyAuditSink`) and is shared across all modules; this
    domain model is only for the admin audit-logs query API.
    """

    id: UUID
    actor_id: UUID | None
    action: str
    object_type: str | None
    object_id: UUID | None
    result: str
    request_id: str | None
    context_data: dict[str, str | int | bool] | None
    created_at: datetime
    detail: str | None

    def __post_init__(self) -> None:
        if not self.action.strip() or not self.result.strip():
            raise ValueError("audit log action and result must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("audit log created_at must be timezone-aware")


__all__ = ["AuditLogEntry"]
