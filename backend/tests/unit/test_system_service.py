from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from knowagent.common.errors import ConflictError, ValidationError
from knowagent.identity.domain.models import AccountRole, AccountStatus
from knowagent.systems.application.system_service import SystemService
from knowagent.systems.domain.models import (
    BusinessSystem,
    BusinessSystemStatus,
    SystemOwner,
    SystemRole,
    SystemRoleAssignment,
)


class SystemRepositoryFake:
    def __init__(self) -> None:
        self.items: dict[UUID, BusinessSystem] = {}
        self.owners: dict[UUID, set[UUID]] = {}

    def get_by_id(self, system_id: UUID) -> BusinessSystem | None:
        item = self.items.get(system_id)
        if item is None:
            return None
        owners = tuple(
            SystemOwner(account_id=value, username="owner", display_name="Owner")
            for value in self.owners.get(system_id, set())
        )
        return replace(item, owners=owners)

    def get_by_code(self, code: str) -> BusinessSystem | None:
        return next((item for item in self.items.values() if item.code == code), None)

    def add(self, business_system: BusinessSystem) -> BusinessSystem:
        self.items[business_system.id] = business_system
        return business_system

    def save(self, business_system: BusinessSystem) -> BusinessSystem:
        self.items[business_system.id] = business_system
        return business_system

    def list(
        self, *, status: BusinessSystemStatus | None, include_owners: bool = True
    ) -> list[BusinessSystem]:
        items = [item for item in self.items.values() if status is None or item.status is status]
        if not include_owners:
            return items
        return [self.get_by_id(item.id) or item for item in items]

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: BusinessSystemStatus | None,
    ) -> tuple[list[BusinessSystem], int]:
        items = self.list(status=status)
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    def assign_owners(
        self, system_id: UUID, account_ids: list[UUID], *, replace_existing: bool
    ) -> list[SystemOwner]:
        target = self.owners.setdefault(system_id, set())
        if replace_existing:
            target.clear()
        target.update(account_ids)
        return [
            SystemOwner(account_id=value, username="owner", display_name="Owner")
            for value in target
        ]

    def list_system_roles(self, account_id: UUID) -> list[SystemRoleAssignment]:
        return [
            SystemRoleAssignment(system_id=system_id, role=SystemRole.SYSTEM_OWNER)
            for system_id, owners in self.owners.items()
            if account_id in owners
        ]


class AccountDirectoryFake:
    def __init__(self) -> None:
        self.roles: dict[UUID, tuple[AccountRole, AccountStatus]] = {}

    def get_roles(self, account_ids: list[UUID]) -> dict[UUID, tuple[AccountRole, AccountStatus]]:
        return {
            account_id: self.roles[account_id]
            for account_id in account_ids
            if account_id in self.roles
        }


class AuditSinkFake:
    def record(self, action: str, result: str, **_: object) -> None:
        del action, result


class SessionStoreFake:
    def __init__(self) -> None:
        self.revoked: list[UUID] = []

    def revoke_account(self, account_id: UUID) -> None:
        self.revoked.append(account_id)


def make_service() -> tuple[
    SystemService, SystemRepositoryFake, AccountDirectoryFake, SessionStoreFake
]:
    systems = SystemRepositoryFake()
    accounts = AccountDirectoryFake()
    sessions = SessionStoreFake()
    service = SystemService(
        systems=systems,
        accounts=accounts,
        sessions=sessions,  # type: ignore[arg-type]
        audit=AuditSinkFake(),
    )
    return service, systems, accounts, sessions


def test_create_system_normalizes_fields_and_rejects_duplicate_code() -> None:
    service, _, _, _ = make_service()
    created = service.create(
        actor_id=uuid4(), code=" esb ", name=" 企业服务总线 ", description=" 集成服务 "
    )

    assert created.code == "ESB"
    assert created.name == "企业服务总线"
    assert created.description == "集成服务"
    with pytest.raises(ConflictError, match="系统标识已存在"):
        service.create(actor_id=uuid4(), code="ESB", name="重复", description=None)


def test_update_system_rejects_empty_payload_and_unknown_system() -> None:
    service, _, _, _ = make_service()

    with pytest.raises(ValidationError, match="至少提供一个"):
        service.update(actor_id=uuid4(), system_id=uuid4())
    with pytest.raises(ValidationError, match="业务系统不存在"):
        service.update(actor_id=uuid4(), system_id=uuid4(), name="新名称")


def test_assign_owners_requires_active_system_owner_accounts() -> None:
    service, _, accounts, sessions = make_service()
    created = service.create(actor_id=uuid4(), code="ESB", name="ESB", description=None)
    owner_id = uuid4()
    disabled_owner_id = uuid4()
    accounts.roles[owner_id] = (AccountRole.SYSTEM_OWNER, AccountStatus.ACTIVE)
    accounts.roles[disabled_owner_id] = (AccountRole.SYSTEM_OWNER, AccountStatus.DISABLED)

    assigned = service.assign_owners(
        actor_id=uuid4(), system_id=created.id, account_ids=[owner_id], replace_existing=True
    )
    assert [owner.account_id for owner in assigned] == [owner_id]
    assert sessions.revoked == [owner_id]
    with pytest.raises(ValidationError, match="有效的系统负责人"):
        service.assign_owners(
            actor_id=uuid4(),
            system_id=created.id,
            account_ids=[disabled_owner_id],
            replace_existing=True,
        )


def test_assign_owners_revokes_only_accounts_whose_mapping_changed() -> None:
    service, _, accounts, sessions = make_service()
    created = service.create(actor_id=uuid4(), code="ESB", name="ESB", description=None)
    first_owner_id = uuid4()
    second_owner_id = uuid4()
    accounts.roles[first_owner_id] = (AccountRole.SYSTEM_OWNER, AccountStatus.ACTIVE)
    accounts.roles[second_owner_id] = (AccountRole.SYSTEM_OWNER, AccountStatus.ACTIVE)

    service.assign_owners(
        actor_id=uuid4(),
        system_id=created.id,
        account_ids=[first_owner_id],
        replace_existing=True,
    )
    sessions.revoked.clear()
    service.assign_owners(
        actor_id=uuid4(),
        system_id=created.id,
        account_ids=[first_owner_id],
        replace_existing=True,
    )
    assert sessions.revoked == []

    service.assign_owners(
        actor_id=uuid4(),
        system_id=created.id,
        account_ids=[second_owner_id],
        replace_existing=True,
    )
    assert set(sessions.revoked) == {first_owner_id, second_owner_id}
