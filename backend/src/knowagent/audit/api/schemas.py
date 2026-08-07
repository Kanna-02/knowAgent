from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    actor_id: UUID | None = None
    action: str
    object_type: str | None = None
    object_id: UUID | None = None
    result: str
    request_id: str | None = None
    context_data: dict[str, str | int | bool] | None = None
    created_at: datetime
    detail: str | None = None


class AuditLogPage(BaseModel):
    items: list[AuditLogView]
    page: int
    page_size: int
    total: int
