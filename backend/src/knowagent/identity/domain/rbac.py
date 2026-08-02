from __future__ import annotations

from enum import StrEnum

from knowagent.identity.domain.models import AccountRole


class Permission(StrEnum):
    USE_USER_APP = "USE_USER_APP"
    USE_ADMIN_APP = "USE_ADMIN_APP"
    MANAGE_OWN_TICKETS = "MANAGE_OWN_TICKETS"
    MANAGE_OWNED_SYSTEMS = "MANAGE_OWNED_SYSTEMS"
    MANAGE_SYSTEM_TICKETS = "MANAGE_SYSTEM_TICKETS"
    MANAGE_ACCOUNTS = "MANAGE_ACCOUNTS"
    MANAGE_PLATFORM = "MANAGE_PLATFORM"


_ROLE_PERMISSIONS: dict[AccountRole, frozenset[Permission]] = {
    AccountRole.USER: frozenset(
        {
            Permission.USE_USER_APP,
            Permission.MANAGE_OWN_TICKETS,
        }
    ),
    AccountRole.SYSTEM_OWNER: frozenset(
        {
            Permission.USE_USER_APP,
            Permission.MANAGE_OWN_TICKETS,
            Permission.MANAGE_OWNED_SYSTEMS,
            Permission.MANAGE_SYSTEM_TICKETS,
        }
    ),
    AccountRole.ADMIN: frozenset(
        {
            Permission.USE_ADMIN_APP,
            Permission.MANAGE_ACCOUNTS,
            Permission.MANAGE_PLATFORM,
        }
    ),
}


def permissions_for(role: AccountRole) -> frozenset[Permission]:
    return _ROLE_PERMISSIONS[role]
