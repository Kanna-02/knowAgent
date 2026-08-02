from knowagent.identity.domain.models import AccountRole
from knowagent.identity.domain.rbac import Permission, permissions_for


def test_user_permissions_only_include_personal_workspace_actions() -> None:
    permissions = permissions_for(AccountRole.USER)

    assert Permission.USE_USER_APP in permissions
    assert Permission.MANAGE_OWN_TICKETS in permissions
    assert Permission.MANAGE_ACCOUNTS not in permissions


def test_system_owner_permissions_include_owned_system_management() -> None:
    permissions = permissions_for(AccountRole.SYSTEM_OWNER)

    assert Permission.MANAGE_OWNED_SYSTEMS in permissions
    assert Permission.MANAGE_SYSTEM_TICKETS in permissions
    assert Permission.MANAGE_ACCOUNTS not in permissions


def test_admin_permissions_include_platform_account_management() -> None:
    permissions = permissions_for(AccountRole.ADMIN)

    assert Permission.USE_ADMIN_APP in permissions
    assert Permission.MANAGE_ACCOUNTS in permissions
    assert Permission.MANAGE_PLATFORM in permissions
