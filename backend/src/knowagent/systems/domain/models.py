from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class BusinessSystemStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SystemRole(StrEnum):
    SYSTEM_OWNER = "SYSTEM_OWNER"


@dataclass(frozen=True, slots=True)
class SystemOwner:
    account_id: UUID
    username: str
    display_name: str


@dataclass(frozen=True, slots=True)
class SystemRoleAssignment:
    system_id: UUID
    role: SystemRole


@dataclass(frozen=True, slots=True)
class BusinessSystem:
    id: UUID
    code: str
    name: str
    description: str | None
    status: BusinessSystemStatus
    created_at: datetime
    updated_at: datetime
    owners: tuple[SystemOwner, ...] = field(default_factory=tuple)
