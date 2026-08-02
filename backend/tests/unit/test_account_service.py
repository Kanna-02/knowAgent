from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from knowagent.common.errors import ConflictError, ValidationError
from knowagent.identity.application.account_service import AccountService
from knowagent.identity.domain.models import Account, AccountRole, AccountSource, AccountStatus


class AccountRepositoryFake:
    def __init__(self, account: Account) -> None:
        self.account = account
        self.locked = False

    def get_by_username(self, username: str) -> Account | None:
        return self.account if self.account.username == username else None

    def get_by_id(self, account_id: UUID) -> Account | None:
        return self.account if self.account.id == account_id else None

    def add(self, account: Account) -> Account:
        self.account = account
        return account

    def save(self, account: Account) -> Account:
        self.account = account
        return account

    def count_active_admins(self) -> int:
        return 2

    def lock_active_admins(self) -> int:
        self.locked = True
        return 1


class PasswordHasherFake:
    dummy_hash = "hashed:dummy"

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == self.hash(password)


class SessionStoreFake:
    def __init__(self) -> None:
        self.revoked: list[UUID] = []

    def revoke_account(self, account_id: UUID) -> None:
        self.revoked.append(account_id)


class AuditSinkFake:
    def record(self, action: str, result: str, **_: object) -> None:
        del action, result


def make_admin() -> Account:
    now = datetime.now(UTC)
    return Account(
        id=uuid4(),
        username="admin",
        display_name="Admin",
        password_hash="hashed:Temporary1!",
        role=AccountRole.ADMIN,
        source=AccountSource.ADMIN_CREATED,
        status=AccountStatus.ACTIVE,
        must_change_password=False,
        session_version=1,
        credential_batch=None,
        external_provider=None,
        external_subject=None,
        created_at=now,
        updated_at=now,
    )


def make_service() -> tuple[AccountService, AccountRepositoryFake, SessionStoreFake]:
    accounts = AccountRepositoryFake(make_admin())
    sessions = SessionStoreFake()
    return (
        AccountService(
            accounts=accounts,
            passwords=PasswordHasherFake(),
            sessions=sessions,  # type: ignore[arg-type]
            audit=AuditSinkFake(),
        ),
        accounts,
        sessions,
    )


def test_set_status_locks_active_admins_before_enforcing_last_admin() -> None:
    service, accounts, sessions = make_service()

    with pytest.raises(ConflictError, match="最后一个有效管理员"):
        service.set_status(
            actor_id=uuid4(),
            account_id=accounts.account.id,
            status=AccountStatus.DISABLED,
        )

    assert accounts.locked is True
    assert sessions.revoked == []


def test_create_admin_rejects_invalid_username() -> None:
    service, _, _ = make_service()

    with pytest.raises(ValidationError, match="账号格式不正确"):
        service.create_admin(
            actor_id=uuid4(),
            username="x",
            display_name="Second Admin",
            temporary_password="Temporary22@",
        )
