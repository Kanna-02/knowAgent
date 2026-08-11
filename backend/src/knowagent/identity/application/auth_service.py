from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from knowagent.common.errors import AuthenticationError, AuthorizationError, ValidationError
from knowagent.identity.domain.models import Account, AccountRole, AccountStatus
from knowagent.identity.ports import (
    AccountRepository,
    AuditSink,
    LoginRateLimiter,
    NewSession,
    PasswordHasher,
    SessionRecord,
    SessionStore,
)


class LoginEntry(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class AuthResult:
    account: Account
    session: NewSession


class AuthService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        passwords: PasswordHasher,
        sessions: SessionStore,
        audit: AuditSink,
        rate_limiter: LoginRateLimiter,
        session_ttl_seconds: int,
    ) -> None:
        self._accounts = accounts
        self._passwords = passwords
        self._sessions = sessions
        self._audit = audit
        self._rate_limiter = rate_limiter
        self._session_ttl_seconds = session_ttl_seconds

    def login(
        self,
        *,
        username: str,
        password: str,
        entry: LoginEntry,
        source_ip: str,
        request_id: str | None = None,
    ) -> AuthResult:
        normalized_username = username.strip().lower()
        if not self._rate_limiter.allow(normalized_username, source_ip, entry.value):
            self._audit.record(
                "auth.login",
                "rate_limited",
                request_id=request_id,
                metadata={"entry": entry.value},
            )
            raise AuthenticationError("AUTH_RATE_LIMITED", "登录尝试过于频繁，请稍后再试")

        account = self._accounts.get_by_username(normalized_username)
        password_hash = account.password_hash if account else self._passwords.dummy_hash
        password_valid = self._passwords.verify(password, password_hash)
        if not password_valid or account is None or not self._entry_allows(entry, account):
            self._rate_limiter.record_failure(normalized_username, source_ip, entry.value)
            self._audit.record(
                "auth.login",
                "failure",
                request_id=request_id,
                metadata={"entry": entry.value},
            )
            raise AuthenticationError()

        self._rate_limiter.reset_account(normalized_username, entry.value)
        session = self._new_session(account)
        self._audit.record(
            "auth.login",
            "success",
            actor_id=account.id,
            object_type="account",
            object_id=account.id,
            request_id=request_id,
            metadata={"entry": entry.value},
        )
        return AuthResult(account=account, session=session)

    def authenticate_session(self, token: str) -> tuple[Account, SessionRecord]:
        record = self._sessions.get(token)
        if record is None:
            raise AuthenticationError("SESSION_INVALID", "登录状态已失效，请重新登录")
        account = self._accounts.get_by_id(record.account_id)
        if (
            account is None
            or account.status is not AccountStatus.ACTIVE
            or account.session_version != record.session_version
        ):
            self._sessions.delete(token)
            raise AuthenticationError("SESSION_INVALID", "登录状态已失效，请重新登录")
        return account, record

    def authorize(self, account: Account, *, allowed_roles: set[AccountRole]) -> None:
        if account.must_change_password:
            raise AuthorizationError("PASSWORD_CHANGE_REQUIRED", "请先修改临时密码")
        if account.role not in allowed_roles:
            raise AuthorizationError()

    def change_password(
        self,
        *,
        account_id: UUID,
        current_password: str,
        new_password: str,
        request_id: str | None = None,
    ) -> AuthResult:
        account = self._accounts.get_by_id(account_id)
        if account is None or not self._passwords.verify(current_password, account.password_hash):
            raise AuthenticationError("CURRENT_PASSWORD_INVALID", "当前密码不正确")
        violations = password_violations(new_password)
        if violations:
            raise ValidationError("PASSWORD_POLICY", "；".join(violations))
        if self._passwords.verify(new_password, account.password_hash):
            raise ValidationError("PASSWORD_REUSED", "新密码不能与当前密码相同")

        now = datetime.now(UTC)
        updated = replace(
            account,
            password_hash=self._passwords.hash(new_password),
            must_change_password=False,
            session_version=account.session_version + 1,
            updated_at=now,
        )
        updated = self._accounts.save(updated)
        self._sessions.revoke_account(account.id)
        session = self._new_session(updated)
        self._audit.record(
            "auth.password.change",
            "success",
            actor_id=updated.id,
            object_type="account",
            object_id=updated.id,
            request_id=request_id,
        )
        return AuthResult(account=updated, session=session)

    def logout(
        self,
        *,
        token: str,
        account_id: UUID,
        request_id: str | None = None,
    ) -> None:
        self._sessions.delete(token)
        self._audit.record(
            "auth.logout",
            "success",
            actor_id=account_id,
            object_type="account",
            object_id=account_id,
            request_id=request_id,
        )

    def _new_session(self, account: Account) -> NewSession:
        expires_at = datetime.now(UTC) + timedelta(seconds=self._session_ttl_seconds)
        return self._sessions.create(
            SessionRecord(
                account_id=account.id,
                session_version=account.session_version,
                csrf_token="",
                expires_at=expires_at,
            )
        )

    @staticmethod
    def _entry_allows(entry: LoginEntry, account: Account) -> bool:
        if account.status is not AccountStatus.ACTIVE:
            return False
        if entry is LoginEntry.ADMIN:
            return account.role is AccountRole.ADMIN
        return account.role in {AccountRole.USER, AccountRole.SYSTEM_OWNER}


def password_violations(password: str) -> list[str]:
    checks = (
        (len(password) >= 8, "至少 8 个字符"),
        (any(character.isalpha() for character in password), "包含字母"),
        (any(character.isdigit() for character in password), "包含数字"),
    )
    return [message for valid, message in checks if not valid]
