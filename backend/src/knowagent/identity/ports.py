from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowagent.identity.domain.models import Account, AccountRole, AccountStatus


@dataclass(frozen=True, slots=True)
class SessionRecord:
    account_id: UUID
    session_version: int
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class NewSession:
    token: str
    csrf_token: str
    expires_at: datetime


class AccountRepository(Protocol):
    def get_by_username(self, username: str) -> Account | None: ...

    def get_by_id(self, account_id: UUID) -> Account | None: ...

    def save(self, account: Account) -> Account: ...

    def add(self, account: Account) -> Account: ...

    def list(
        self,
        *,
        page: int,
        page_size: int,
        role: AccountRole | None,
        status: AccountStatus | None,
    ) -> tuple[list[Account], int]: ...

    def count_active_admins(self) -> int: ...

    def lock_active_admins(self) -> int: ...


class PasswordHasher(Protocol):
    @property
    def dummy_hash(self) -> str: ...

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class SessionStore(Protocol):
    def create(self, record: SessionRecord) -> NewSession: ...

    def get(self, token: str) -> SessionRecord | None: ...

    def delete(self, token: str) -> None: ...

    def revoke_account(self, account_id: UUID) -> None: ...


class AuditSink(Protocol):
    def record(
        self,
        action: str,
        result: str,
        *,
        actor_id: UUID | None = None,
        object_type: str | None = None,
        object_id: UUID | None = None,
        request_id: str | None = None,
        metadata: dict[str, str | int | bool] | None = None,
    ) -> None: ...


class LoginRateLimiter(Protocol):
    def allow(self, username: str, source_ip: str, entry: str) -> bool: ...

    def record_failure(self, username: str, source_ip: str, entry: str) -> None: ...

    def reset_account(self, username: str, entry: str) -> None: ...


class IdentityProvider(Protocol):
    @property
    def name(self) -> str: ...

    def authorization_url(self, redirect_uri: str) -> str: ...

    def resolve_callback(self, query: dict[str, str]) -> tuple[str, str]: ...
