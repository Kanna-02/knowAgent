from __future__ import annotations

from dataclasses import replace
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


@pytest.mark.parametrize("role", [AccountRole.USER, AccountRole.SYSTEM_OWNER])
def test_create_account_supports_user_and_system_owner(role: AccountRole) -> None:
    service, accounts, _ = make_service()

    created = service.create_account(
        actor_id=uuid4(),
        username="new.user",
        display_name="New User",
        temporary_password="welcome1",
        role=role,
    )

    assert accounts.account == created
    assert created.role is role
    assert created.source is AccountSource.ADMIN_CREATED
    assert created.must_change_password is True
    assert created.password_hash == "hashed:welcome1"


def test_set_role_rotates_sessions_and_persists_role_change() -> None:
    service, accounts, sessions = make_service()
    accounts.account = replace(accounts.account, role=AccountRole.USER)

    updated = service.set_role(
        actor_id=uuid4(),
        account_id=accounts.account.id,
        role=AccountRole.SYSTEM_OWNER,
    )

    assert updated.role is AccountRole.SYSTEM_OWNER
    assert updated.session_version == 2
    assert sessions.revoked == [updated.id]


def test_set_role_rejects_removing_the_last_active_admin() -> None:
    service, accounts, sessions = make_service()

    with pytest.raises(ConflictError, match="最后一个有效管理员"):
        service.set_role(
            actor_id=uuid4(),
            account_id=accounts.account.id,
            role=AccountRole.USER,
        )

    assert accounts.locked is True
    assert sessions.revoked == []
