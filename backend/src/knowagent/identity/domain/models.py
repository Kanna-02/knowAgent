from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AccountRole(StrEnum):
    USER = "USER"
    SYSTEM_OWNER = "SYSTEM_OWNER"
    ADMIN = "ADMIN"


class AccountSource(StrEnum):
    LOCAL_IMPORT = "LOCAL_IMPORT"
    ADMIN_CREATED = "ADMIN_CREATED"
    SSO = "SSO"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    username: str
    display_name: str
    password_hash: str
    role: AccountRole
    source: AccountSource
    status: AccountStatus
    must_change_password: bool
    session_version: int
    credential_batch: str | None
    external_provider: str | None
    external_subject: str | None
    created_at: datetime
    updated_at: datetime
