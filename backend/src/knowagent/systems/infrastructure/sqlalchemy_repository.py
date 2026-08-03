from __future__ import annotations

import builtins
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowagent.common.errors import ConflictError
from knowagent.identity.domain.models import AccountRole, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
from knowagent.systems.domain.models import (
    BusinessSystem,
    BusinessSystemStatus,
    SystemOwner,
    SystemRole,
    SystemRoleAssignment,
)
from knowagent.systems.infrastructure.sqlalchemy_models import (
    AccountSystemRoleRecord,
    BusinessSystemRecord,
)


class SqlAlchemySystemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, system_id: UUID) -> BusinessSystem | None:
        record = self._session.get(BusinessSystemRecord, system_id)
        if record is None:
            return None
        return self._to_domain(record, self._owners_by_system([record.id]).get(record.id, ()))

    def get_by_code(self, code: str) -> BusinessSystem | None:
        record = self._session.scalar(
            select(BusinessSystemRecord).where(BusinessSystemRecord.code == code)
        )
        if record is None:
            return None
        return self._to_domain(record, self._owners_by_system([record.id]).get(record.id, ()))

    def add(self, business_system: BusinessSystem) -> BusinessSystem:
        record = BusinessSystemRecord(
            id=business_system.id,
            code=business_system.code,
            name=business_system.name,
            description=business_system.description,
            status=business_system.status,
            created_at=business_system.created_at,
            updated_at=business_system.updated_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            raise ConflictError("SYSTEM_EXISTS", "系统标识已存在") from error
        return self._to_domain(record)

    def save(self, business_system: BusinessSystem) -> BusinessSystem:
        record = self._session.get(BusinessSystemRecord, business_system.id)
        if record is None:
            raise ConflictError("SYSTEM_NOT_FOUND", "业务系统不存在")
        record.name = business_system.name
        record.description = business_system.description
        record.status = business_system.status
        record.updated_at = business_system.updated_at
        self._session.flush()
        return self._to_domain(record, self._owners_by_system([record.id]).get(record.id, ()))

    def list(
        self,
        *,
        status: BusinessSystemStatus | None,
        include_owners: bool = True,
    ) -> builtins.list[BusinessSystem]:
        statement = select(BusinessSystemRecord)
        if status is not None:
            statement = statement.where(BusinessSystemRecord.status == status)
        records = self._session.scalars(statement.order_by(BusinessSystemRecord.code)).all()
        owners = self._owners_by_system([record.id for record in records]) if include_owners else {}
        return [self._to_domain(record, owners.get(record.id, ())) for record in records]

    def list_page(
        self,
        *,
        page: int,
        page_size: int,
        status: BusinessSystemStatus | None,
    ) -> tuple[builtins.list[BusinessSystem], int]:
        filters = []
        if status is not None:
            filters.append(BusinessSystemRecord.status == status)
        total = self._session.scalar(
            select(func.count()).select_from(BusinessSystemRecord).where(*filters)
        )
        records = self._session.scalars(
            select(BusinessSystemRecord)
            .where(*filters)
            .order_by(BusinessSystemRecord.code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        owners = self._owners_by_system([record.id for record in records])
        return (
            [self._to_domain(record, owners.get(record.id, ())) for record in records],
            int(total or 0),
        )

    def assign_owners(
        self,
        system_id: UUID,
        account_ids: builtins.list[UUID],
        *,
        replace_existing: bool,
    ) -> builtins.list[SystemOwner]:
        if replace_existing:
            self._session.execute(
                delete(AccountSystemRoleRecord).where(
                    AccountSystemRoleRecord.system_id == system_id,
                    AccountSystemRoleRecord.role == SystemRole.SYSTEM_OWNER,
                )
            )
            existing: set[UUID] = set()
        else:
            existing = set(
                self._session.scalars(
                    select(AccountSystemRoleRecord.account_id).where(
                        AccountSystemRoleRecord.system_id == system_id,
                        AccountSystemRoleRecord.role == SystemRole.SYSTEM_OWNER,
                    )
                ).all()
            )
        for account_id in account_ids:
            if account_id not in existing:
                self._session.add(
                    AccountSystemRoleRecord(
                        account_id=account_id,
                        system_id=system_id,
                        role=SystemRole.SYSTEM_OWNER,
                    )
                )
        self._session.flush()
        return builtins.list(self._owners_by_system([system_id]).get(system_id, ()))

    def list_system_roles(self, account_id: UUID) -> builtins.list[SystemRoleAssignment]:
        rows = self._session.execute(
            select(AccountSystemRoleRecord.system_id, AccountSystemRoleRecord.role)
            .where(AccountSystemRoleRecord.account_id == account_id)
            .order_by(AccountSystemRoleRecord.system_id, AccountSystemRoleRecord.role)
        ).all()
        return [SystemRoleAssignment(system_id=system_id, role=role) for system_id, role in rows]

    def _owners_by_system(
        self, system_ids: builtins.list[UUID]
    ) -> dict[UUID, tuple[SystemOwner, ...]]:
        if not system_ids:
            return {}
        rows = self._session.execute(
            select(
                AccountSystemRoleRecord.system_id,
                AccountRecord.id,
                AccountRecord.username,
                AccountRecord.display_name,
            )
            .join(AccountRecord, AccountRecord.id == AccountSystemRoleRecord.account_id)
            .where(
                AccountSystemRoleRecord.system_id.in_(system_ids),
                AccountSystemRoleRecord.role == SystemRole.SYSTEM_OWNER,
            )
            .order_by(AccountRecord.display_name, AccountRecord.username)
        ).all()
        grouped: defaultdict[UUID, builtins.list[SystemOwner]] = defaultdict(builtins.list)
        for system_id, account_id, username, display_name in rows:
            grouped[system_id].append(
                SystemOwner(
                    account_id=account_id,
                    username=username,
                    display_name=display_name,
                )
            )
        return {system_id: tuple(items) for system_id, items in grouped.items()}

    @staticmethod
    def _to_domain(
        record: BusinessSystemRecord, owners: tuple[SystemOwner, ...] = ()
    ) -> BusinessSystem:
        return BusinessSystem(
            id=record.id,
            code=record.code,
            name=record.name,
            description=record.description,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            owners=owners,
        )


class SqlAlchemyAccountDirectory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_roles(
        self, account_ids: builtins.list[UUID]
    ) -> dict[UUID, tuple[AccountRole, AccountStatus]]:
        if not account_ids:
            return {}
        rows = self._session.execute(
            select(AccountRecord.id, AccountRecord.role, AccountRecord.status).where(
                AccountRecord.id.in_(account_ids)
            )
        ).all()
        return {account_id: (role, status) for account_id, role, status in rows}
