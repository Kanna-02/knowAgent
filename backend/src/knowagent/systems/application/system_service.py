from __future__ import annotations

import builtins
import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from knowagent.common.errors import ConflictError, ValidationError
from knowagent.identity.domain.models import AccountRole, AccountStatus
from knowagent.identity.ports import AuditSink, SessionStore
from knowagent.systems.domain.models import BusinessSystem, BusinessSystemStatus, SystemOwner
from knowagent.systems.ports import AccountDirectory, SystemRepository

_SYSTEM_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,31}$")


class SystemService:
    def __init__(
        self,
        *,
        systems: SystemRepository,
        accounts: AccountDirectory,
        sessions: SessionStore,
        audit: AuditSink,
    ) -> None:
        self._systems = systems
        self._accounts = accounts
        self._sessions = sessions
        self._audit = audit

    def create(
        self,
        *,
        actor_id: UUID,
        code: str,
        name: str,
        description: str | None,
        status: BusinessSystemStatus = BusinessSystemStatus.ACTIVE,
        request_id: str | None = None,
    ) -> BusinessSystem:
        normalized_code = self._normalize_code(code)
        normalized_name = self._normalize_name(name)
        normalized_description = self._normalize_description(description)
        if self._systems.get_by_code(normalized_code) is not None:
            raise ConflictError("SYSTEM_EXISTS", "系统标识已存在")
        now = datetime.now(UTC)
        created = self._systems.add(
            BusinessSystem(
                id=uuid4(),
                code=normalized_code,
                name=normalized_name,
                description=normalized_description,
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        self._audit.record(
            "system.create",
            "success",
            actor_id=actor_id,
            object_type="business_system",
            object_id=created.id,
            request_id=request_id,
            metadata={"code": created.code, "status": created.status.value},
        )
        return created

    def update(
        self,
        *,
        actor_id: UUID,
        system_id: UUID,
        name: str | None = None,
        description: str | None = None,
        description_is_set: bool = False,
        status: BusinessSystemStatus | None = None,
        request_id: str | None = None,
    ) -> BusinessSystem:
        if name is None and not description_is_set and status is None:
            raise ValidationError("SYSTEM_UPDATE_EMPTY", "至少提供一个需要更新的字段")
        current = self._systems.get_by_id(system_id)
        if current is None:
            raise ValidationError("SYSTEM_NOT_FOUND", "业务系统不存在")
        updated = replace(
            current,
            name=self._normalize_name(name) if name is not None else current.name,
            description=(
                self._normalize_description(description)
                if description_is_set
                else current.description
            ),
            status=status if status is not None else current.status,
            updated_at=datetime.now(UTC),
        )
        updated = self._systems.save(updated)
        self._audit.record(
            "system.update",
            "success",
            actor_id=actor_id,
            object_type="business_system",
            object_id=updated.id,
            request_id=request_id,
            metadata={"status": updated.status.value},
        )
        return updated

    def list(
        self,
        *,
        status: BusinessSystemStatus | None,
        include_owners: bool = True,
    ) -> builtins.list[BusinessSystem]:
        return self._systems.list(status=status, include_owners=include_owners)

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: BusinessSystemStatus | None,
    ) -> tuple[builtins.list[BusinessSystem], int]:
        return self._systems.list_page(page=page, page_size=page_size, status=status)

    def assign_owners(
        self,
        *,
        actor_id: UUID,
        system_id: UUID,
        account_ids: builtins.list[UUID],
        replace_existing: bool,
        request_id: str | None = None,
    ) -> builtins.list[SystemOwner]:
        current = self._systems.get_by_id(system_id)
        if current is None:
            raise ValidationError("SYSTEM_NOT_FOUND", "业务系统不存在")
        previous_owner_ids = {owner.account_id for owner in current.owners}
        unique_ids: builtins.list[UUID] = builtins.list(dict.fromkeys(account_ids))
        if len(unique_ids) > 100:
            raise ValidationError("SYSTEM_OWNER_LIMIT", "单个系统最多配置 100 位负责人")
        account_roles = self._accounts.get_roles(unique_ids)
        invalid_ids = [
            account_id
            for account_id in unique_ids
            if account_roles.get(account_id) != (AccountRole.SYSTEM_OWNER, AccountStatus.ACTIVE)
        ]
        if invalid_ids:
            raise ValidationError("SYSTEM_OWNER_INVALID", "负责人必须是有效的系统负责人账号")
        owners = self._systems.assign_owners(
            system_id,
            unique_ids,
            replace_existing=replace_existing,
        )
        current_owner_ids = {owner.account_id for owner in owners}
        for account_id in previous_owner_ids.symmetric_difference(current_owner_ids):
            self._sessions.revoke_account(account_id)
        self._audit.record(
            "system.owners.assign",
            "success",
            actor_id=actor_id,
            object_type="business_system",
            object_id=system_id,
            request_id=request_id,
            metadata={"owner_count": len(owners), "replace_existing": replace_existing},
        )
        return owners

    @staticmethod
    def _normalize_code(value: str) -> str:
        code = value.strip().upper()
        if not _SYSTEM_CODE_PATTERN.fullmatch(code):
            raise ValidationError(
                "SYSTEM_CODE_INVALID", "系统标识须为 2-32 位字母、数字、下划线或连字符"
            )
        return code

    @staticmethod
    def _normalize_name(value: str) -> str:
        name = value.strip()
        if not name:
            raise ValidationError("SYSTEM_NAME_INVALID", "系统名称不能为空")
        if len(name) > 100:
            raise ValidationError("SYSTEM_NAME_INVALID", "系统名称不能超过 100 个字符")
        return name

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        if value is None:
            return None
        description = value.strip()
        if len(description) > 500:
            raise ValidationError("SYSTEM_DESCRIPTION_INVALID", "系统说明不能超过 500 个字符")
        return description or None
