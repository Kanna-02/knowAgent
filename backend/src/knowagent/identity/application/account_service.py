from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from knowagent.common.errors import ConflictError, ValidationError
from knowagent.identity.application.auth_service import password_violations
from knowagent.identity.domain.account_validation import normalize_display_name, normalize_username
from knowagent.identity.domain.models import Account, AccountRole, AccountSource, AccountStatus
from knowagent.identity.ports import AccountRepository, AuditSink, PasswordHasher, SessionStore


class AccountService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        passwords: PasswordHasher,
        sessions: SessionStore,
        audit: AuditSink,
    ) -> None:
        self._accounts = accounts
        self._passwords = passwords
        self._sessions = sessions
        self._audit = audit

    def create_admin(
        self,
        *,
        actor_id: UUID,
        username: str,
        display_name: str,
        temporary_password: str,
        request_id: str | None = None,
    ) -> Account:
        return self.create_account(
            actor_id=actor_id,
            username=username,
            display_name=display_name,
            temporary_password=temporary_password,
            role=AccountRole.ADMIN,
            request_id=request_id,
        )

    def create_account(  # pylint: disable=too-many-arguments
        self,
        *,
        actor_id: UUID,
        username: str,
        display_name: str,
        temporary_password: str,
        role: AccountRole,
        request_id: str | None = None,
    ) -> Account:
        try:
            normalized_username = normalize_username(username)
            normalized_display_name = normalize_display_name(display_name)
        except ValueError as error:
            raise ValidationError("ACCOUNT_INVALID", str(error)) from error
        if self._accounts.get_by_username(normalized_username) is not None:
            raise ConflictError("ACCOUNT_EXISTS", "账号已存在")
        violations = password_violations(temporary_password)
        if violations:
            raise ValidationError("PASSWORD_POLICY", "；".join(violations))
        now = datetime.now(UTC)
        account = Account(
            id=uuid4(),
            username=normalized_username,
            display_name=normalized_display_name,
            password_hash=self._passwords.hash(temporary_password),
            role=role,
            source=AccountSource.ADMIN_CREATED,
            status=AccountStatus.ACTIVE,
            must_change_password=True,
            session_version=1,
            credential_batch=None,
            external_provider=None,
            external_subject=None,
            created_at=now,
            updated_at=now,
        )
        created = self._accounts.add(account)
        self._audit.record(
            "account.admin.create" if role is AccountRole.ADMIN else "account.user.create",
            "success",
            actor_id=actor_id,
            object_type="account",
            object_id=created.id,
            request_id=request_id,
            metadata={"role": role.value},
        )
        return created

    def list_accounts(
        self,
        *,
        page: int,
        page_size: int,
        role: AccountRole | None,
        status: AccountStatus | None,
        search: str | None,
    ) -> tuple[list[Account], int]:
        return self._accounts.list(
            page=page,
            page_size=page_size,
            role=role,
            status=status,
            search=search,
        )

    def set_status(
        self,
        *,
        actor_id: UUID,
        account_id: UUID,
        status: AccountStatus,
        request_id: str | None = None,
    ) -> Account:
        account = self._accounts.get_by_id(account_id)
        if account is None:
            raise ValidationError("ACCOUNT_NOT_FOUND", "账号不存在")
        if (
            account.role is AccountRole.ADMIN
            and status is AccountStatus.DISABLED
            and self._accounts.lock_active_admins() <= 1
        ):
            raise ConflictError("LAST_ADMIN", "不能禁用最后一个有效管理员")
        updated = replace(
            account,
            status=status,
            session_version=account.session_version + 1,
            updated_at=datetime.now(UTC),
        )
        updated = self._accounts.save(updated)
        self._sessions.revoke_account(account.id)
        self._audit.record(
            "account.status.change",
            "success",
            actor_id=actor_id,
            object_type="account",
            object_id=updated.id,
            request_id=request_id,
            metadata={"status": status.value},
        )
        return updated

    def set_role(
        self,
        *,
        actor_id: UUID,
        account_id: UUID,
        role: AccountRole,
        request_id: str | None = None,
    ) -> Account:
        account = self._accounts.get_by_id(account_id)
        if account is None:
            raise ValidationError("ACCOUNT_NOT_FOUND", "账号不存在")
        if account.role is AccountRole.ADMIN and role is not AccountRole.ADMIN:
            if account.status is AccountStatus.ACTIVE and self._accounts.lock_active_admins() <= 1:
                raise ConflictError("LAST_ADMIN", "不能移除最后一个有效管理员")
        if account.role is role:
            return account
        updated = replace(
            account,
            role=role,
            session_version=account.session_version + 1,
            updated_at=datetime.now(UTC),
        )
        updated = self._accounts.save(updated)
        self._sessions.revoke_account(account.id)
        self._audit.record(
            "account.role.change",
            "success",
            actor_id=actor_id,
            object_type="account",
            object_id=updated.id,
            request_id=request_id,
            metadata={"old_role": account.role.value, "role": role.value},
        )
        return updated
