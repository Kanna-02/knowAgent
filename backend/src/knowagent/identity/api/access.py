from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from knowagent.common.errors import AuthorizationError, NotFoundError
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.systems.domain.models import BusinessSystemStatus, SystemRole, SystemRoleAssignment
from knowagent.systems.infrastructure.sqlalchemy_repository import SqlAlchemySystemRepository


def require_system_access(
    *,
    system_id: UUID,
    account: Account,
    database: Session,
    allow_user: bool = False,
) -> None:
    """Authorize access to a single business system.

    ADMIN sees every system. SYSTEM_OWNER must own ``system_id``. When
    ``allow_user`` is True a USER may access an ACTIVE system; otherwise USER
    callers are rejected (used by management endpoints). Missing systems raise
    NotFoundError, mirroring the per-router helpers this replaces.
    """
    systems = SqlAlchemySystemRepository(database)
    system = systems.get_by_id(system_id)
    if system is None:
        raise NotFoundError("SYSTEM_NOT_FOUND", "业务系统不存在")
    if account.role is AccountRole.ADMIN:
        return
    if account.role is AccountRole.SYSTEM_OWNER:
        roles: list[SystemRoleAssignment] = systems.list_system_roles(account.id)
        if any(
            assignment.system_id == system_id and assignment.role is SystemRole.SYSTEM_OWNER
            for assignment in roles
        ):
            return
        raise AuthorizationError("SYSTEM_ACCESS_DENIED", "没有该业务系统的管理权限")
    # USER role.

    if not allow_user:
        raise AuthorizationError("SYSTEM_ACCESS_DENIED", "没有该业务系统的管理权限")
    if system.status is not BusinessSystemStatus.ACTIVE:
        raise AuthorizationError("SYSTEM_ACCESS_DENIED", "业务系统未启用")


def visible_system_ids(
    account: Account,
    database: Session,
) -> list[UUID]:
    """Return the system IDs an account is allowed to see for ticket listing.

    ADMIN sees every system. SYSTEM_OWNER sees the systems they own. USER sees
    every ACTIVE system. The list is unbounded (no paging cap) so callers can
    safely treat an empty result as "no visible systems" rather than a truncated
    page.
    """
    systems = SqlAlchemySystemRepository(database)
    if account.role is AccountRole.ADMIN:
        return [system.id for system in systems.list(status=None, include_owners=False)]
    if account.role is AccountRole.SYSTEM_OWNER:
        roles = systems.list_system_roles(account.id)
        return [
            assignment.system_id
            for assignment in roles
            if assignment.role is SystemRole.SYSTEM_OWNER
        ]
    # USER role: only active systems.

    return [
        system.id
        for system in systems.list(status=BusinessSystemStatus.ACTIVE, include_owners=False)
    ]


__all__ = ["require_system_access", "visible_system_ids"]
