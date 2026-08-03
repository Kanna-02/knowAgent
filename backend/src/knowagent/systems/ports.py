from __future__ import annotations

import builtins
from typing import Protocol
from uuid import UUID

from knowagent.identity.domain.models import AccountRole, AccountStatus
from knowagent.systems.domain.models import (
    BusinessSystem,
    BusinessSystemStatus,
    SystemOwner,
    SystemRoleAssignment,
)


class SystemRepository(Protocol):
    def get_by_id(self, system_id: UUID) -> BusinessSystem | None: ...

    def get_by_code(self, code: str) -> BusinessSystem | None: ...

    def add(self, business_system: BusinessSystem) -> BusinessSystem: ...

    def save(self, business_system: BusinessSystem) -> BusinessSystem: ...

    def list(
        self,
        *,
        status: BusinessSystemStatus | None,
        include_owners: bool = True,
    ) -> builtins.list[BusinessSystem]: ...

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: BusinessSystemStatus | None,
    ) -> tuple[builtins.list[BusinessSystem], int]: ...

    def assign_owners(
        self,
        system_id: UUID,
        account_ids: builtins.list[UUID],
        *,
        replace_existing: bool,
    ) -> builtins.list[SystemOwner]: ...

    def list_system_roles(self, account_id: UUID) -> builtins.list[SystemRoleAssignment]: ...


class AccountDirectory(Protocol):
    def get_roles(
        self, account_ids: list[UUID]
    ) -> dict[UUID, tuple[AccountRole, AccountStatus]]: ...
