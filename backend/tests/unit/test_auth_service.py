from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from knowagent.common.errors import AuthenticationError, AuthorizationError
from knowagent.identity.application.auth_service import AuthService, LoginEntry
from knowagent.identity.domain.models import Account, AccountRole, AccountSource, AccountStatus
from knowagent.identity.ports import NewSession, SessionRecord


class AccountRepositoryFake:
    def __init__(self, accounts: list[Account]) -> None:
        self.accounts = {account.username: account for account in accounts}

    def get_by_username(self, username: str) -> Account | None:
        return self.accounts.get(username)

    def get_by_id(self, account_id: UUID) -> Account | None:
        return next((item for item in self.accounts.values() if item.id == account_id), None)

    def save(self, account: Account) -> Account:
        self.accounts[account.username] = account
        return account

    def count_active_admins(self) -> int:
        return sum(
            account.role is AccountRole.ADMIN and account.status is AccountStatus.ACTIVE
            for account in self.accounts.values()
        )


class PasswordHasherFake:
    dummy_hash = "hashed:dummy"

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == self.hash(password)


class SessionStoreFake:
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}
        self.revoked_accounts: list[UUID] = []

    def create(self, record: SessionRecord) -> NewSession:
        session = NewSession("session-token", "csrf-token", record.expires_at)
        self.records[session.token] = replace(record, csrf_token=session.csrf_token)
        return session

    def get(self, token: str) -> SessionRecord | None:
        return self.records.get(token)

    def delete(self, token: str) -> None:
        self.records.pop(token, None)

    def revoke_account(self, account_id: UUID) -> None:
        self.revoked_accounts.append(account_id)
        self.records = {
            token: record
            for token, record in self.records.items()
            if record.account_id != account_id
        }


class AuditSinkFake:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def record(self, action: str, result: str, **_: object) -> None:
        self.actions.append((action, result))


class RateLimiterFake:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.failures: list[tuple[str, str, str]] = []
        self.resets: list[tuple[str, str]] = []

    def allow(self, username: str, source_ip: str, entry: str) -> bool:
        del username, source_ip, entry
        return self.allowed

    def record_failure(self, username: str, source_ip: str, entry: str) -> None:
        self.failures.append((username, source_ip, entry))

    def reset_account(self, username: str, entry: str) -> None:
        self.resets.append((username, entry))


def make_account(
    role: AccountRole = AccountRole.USER,
    *,
    username: str = "alice",
    status: AccountStatus = AccountStatus.ACTIVE,
    must_change_password: bool = True,
) -> Account:
    now = datetime.now(UTC)
    return Account(
        id=uuid4(),
        username=username,
        display_name="Alice",
        password_hash="hashed:Temporary1!",
        role=role,
        source=AccountSource.LOCAL_IMPORT,
        status=status,
        must_change_password=must_change_password,
        session_version=1,
        credential_batch="batch-001",
        external_provider=None,
        external_subject=None,
        created_at=now,
        updated_at=now,
    )


def make_service(
    accounts: list[Account], *, limiter: RateLimiterFake | None = None
) -> tuple[AuthService, SessionStoreFake, AuditSinkFake]:
    sessions = SessionStoreFake()
    audit = AuditSinkFake()
    service = AuthService(
        accounts=AccountRepositoryFake(accounts),
        passwords=PasswordHasherFake(),
        sessions=sessions,
        audit=audit,
        rate_limiter=limiter or RateLimiterFake(),
        session_ttl_seconds=3600,
    )
    return service, sessions, audit


def test_login_user_entry_returns_restricted_session_for_temporary_password() -> None:
    account = make_account()
    service, _, audit = make_service([account])

    result = service.login(
        username=" Alice ",
        password="Temporary1!",
        entry=LoginEntry.USER,
        source_ip="127.0.0.1",
    )

    assert result.account.id == account.id
    assert result.account.must_change_password is True
    assert result.session.token == "session-token"
    assert audit.actions[-1] == ("auth.login", "success")


@pytest.mark.parametrize(
    ("account", "entry"),
    [
        (make_account(role=AccountRole.ADMIN), LoginEntry.USER),
        (make_account(role=AccountRole.USER), LoginEntry.ADMIN),
        (make_account(status=AccountStatus.DISABLED), LoginEntry.USER),
    ],
)
def test_login_wrong_entry_or_disabled_account_returns_same_authentication_error(
    account: Account, entry: LoginEntry
) -> None:
    service, _, audit = make_service([account])

    with pytest.raises(AuthenticationError) as error:
        service.login(
            username=account.username,
            password="Temporary1!",
            entry=entry,
            source_ip="127.0.0.1",
        )

    assert error.value.code == "AUTH_INVALID"
    assert audit.actions[-1] == ("auth.login", "failure")


def test_login_rate_limited_request_is_rejected_before_authentication() -> None:
    service, _, _ = make_service([make_account()], limiter=RateLimiterFake(allowed=False))

    with pytest.raises(AuthenticationError) as error:
        service.login(
            username="alice",
            password="Temporary1!",
            entry=LoginEntry.USER,
            source_ip="127.0.0.1",
        )

    assert error.value.code == "AUTH_RATE_LIMITED"


def test_change_password_revokes_old_sessions_and_clears_first_change_flag() -> None:
    account = make_account()
    service, sessions, _ = make_service([account])
    login = service.login(
        username="alice",
        password="Temporary1!",
        entry=LoginEntry.USER,
        source_ip="127.0.0.1",
    )

    result = service.change_password(
        account_id=account.id,
        current_password="Temporary1!",
        new_password="Replacement2@",
    )

    assert result.account.must_change_password is False
    assert result.account.session_version == 2
    assert sessions.revoked_accounts == [account.id]
    assert result.session.token == "session-token"
    assert login.session.token == result.session.token


def test_authorize_restricted_session_only_allows_account_recovery_actions() -> None:
    account = make_account()
    service, _, _ = make_service([account])

    with pytest.raises(AuthorizationError) as error:
        service.authorize(account, allowed_roles={AccountRole.USER})

    assert error.value.code == "PASSWORD_CHANGE_REQUIRED"
