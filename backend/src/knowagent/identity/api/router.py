from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from knowagent.identity.api.dependencies import (
    AdminContext,
    AdminCsrfContext,
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
    RedisClient,
    get_password_hasher,
)
from knowagent.identity.api.schemas import (
    AccountCreateRequest,
    AccountPage,
    AccountRoleRequest,
    AccountStatusRequest,
    AccountView,
    ChangePasswordRequest,
    CurrentUserView,
    LoginRequest,
    SessionView,
)
from knowagent.identity.application.account_service import AccountService
from knowagent.identity.application.auth_service import LoginEntry
from knowagent.identity.domain.models import AccountRole, AccountStatus
from knowagent.identity.infrastructure.redis_session import RedisSessionStore
from knowagent.identity.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAuditSink,
)
from knowagent.identity.infrastructure.sso import DisabledIdentityProvider
from knowagent.systems.infrastructure.sqlalchemy_repository import SqlAlchemySystemRepository

router = APIRouter()


@router.post("/auth/user/sessions", response_model=SessionView)
def create_user_session(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> SessionView:
    return _create_session(payload, request, response, auth, LoginEntry.USER, database)


@router.post("/auth/admin/sessions", response_model=SessionView)
def create_admin_session(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> SessionView:
    return _create_session(payload, request, response, auth, LoginEntry.ADMIN, database)


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    request: Request,
    response: Response,
    context: CsrfContext,
    auth: AuthServiceDependency,
) -> None:
    auth.logout(
        token=context.token,
        account_id=context.account.id,
        request_id=request.state.request_id,
    )
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/auth/me", response_model=CurrentUserView)
def get_current_user(
    response: Response,
    context: CurrentContextDependency,
    database: DatabaseSession,
) -> CurrentUserView:
    response.headers["X-CSRF-Token"] = context.session.csrf_token
    return CurrentUserView.from_account(
        context.account,
        SqlAlchemySystemRepository(database).list_system_roles(context.account.id),
    )


@router.post("/auth/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    context: CsrfContext,
    auth: AuthServiceDependency,
) -> None:
    result = auth.change_password(
        account_id=context.account.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        request_id=request.state.request_id,
    )
    _set_session_cookie(request, response, result.session.token, result.session.expires_at)
    response.headers["X-CSRF-Token"] = result.session.csrf_token


@router.post("/admin/accounts", response_model=AccountView, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> AccountView:
    service = _account_service(request, database, redis)
    account = service.create_account(
        actor_id=context.account.id,
        username=payload.username,
        display_name=payload.display_name,
        temporary_password=payload.temporary_password,
        role=payload.role,
        request_id=request.state.request_id,
    )
    return AccountView.from_account(account)


@router.get("/admin/accounts", response_model=AccountPage)
def list_accounts(
    request: Request,
    context: AdminContext,
    database: DatabaseSession,
    redis: RedisClient,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: AccountRole | None = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> AccountPage:
    del context
    items, total = _account_service(request, database, redis).list_accounts(
        page=page,
        page_size=page_size,
        role=role,
        status=account_status,
        search=search,
    )
    return AccountPage(
        items=[AccountView.from_account(account) for account in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.patch("/admin/accounts/{account_id}/status", response_model=AccountView)
def update_account_status(
    account_id: UUID,
    payload: AccountStatusRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> AccountView:
    account = _account_service(request, database, redis).set_status(
        actor_id=context.account.id,
        account_id=account_id,
        status=payload.status,
        request_id=request.state.request_id,
    )
    return AccountView.from_account(account)


@router.patch("/admin/accounts/{account_id}/role", response_model=AccountView)
def update_account_role(
    account_id: UUID,
    payload: AccountRoleRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
    redis: RedisClient,
) -> AccountView:
    account = _account_service(request, database, redis).set_role(
        actor_id=context.account.id,
        account_id=account_id,
        role=payload.role,
        request_id=request.state.request_id,
    )
    return AccountView.from_account(account)


@router.get("/auth/sso/{provider}/start")
def start_sso(provider: str, redirect_uri: str) -> None:
    DisabledIdentityProvider(provider).authorization_url(redirect_uri)


@router.get("/auth/sso/{provider}/callback")
def complete_sso(provider: str, request: Request) -> None:
    DisabledIdentityProvider(provider).resolve_callback(dict(request.query_params))


def _create_session(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDependency,
    entry: LoginEntry,
    database: DatabaseSession,
) -> SessionView:
    source_ip = request.client.host if request.client else "unknown"
    result = auth.login(
        username=payload.username,
        password=payload.password,
        entry=entry,
        source_ip=source_ip,
        request_id=request.state.request_id,
    )
    _set_session_cookie(request, response, result.session.token, result.session.expires_at)
    return SessionView(
        user=CurrentUserView.from_account(
            result.account,
            SqlAlchemySystemRepository(database).list_system_roles(result.account.id),
        ),
        must_change_password=result.account.must_change_password,
        csrf_token=result.session.csrf_token,
        expires_at=result.session.expires_at,
    )


def _set_session_cookie(
    request: Request, response: Response, token: str, expires_at: datetime
) -> None:
    response.set_cookie(
        request.app.state.settings.session_cookie_name,
        token,
        expires=expires_at,
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _account_service(
    request: Request, database: DatabaseSession, redis: RedisClient
) -> AccountService:
    return AccountService(
        accounts=SqlAlchemyAccountRepository(database),
        passwords=get_password_hasher(),
        sessions=RedisSessionStore(redis, prefix=request.app.state.settings.redis_prefix),
        audit=SqlAlchemyAuditSink(database),
    )
