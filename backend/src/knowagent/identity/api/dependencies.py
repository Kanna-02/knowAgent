from __future__ import annotations

import hmac
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from redis import Redis
from sqlalchemy.orm import Session

from knowagent.common.errors import AuthenticationError, AuthorizationError
from knowagent.identity.application.auth_service import AuthService
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.redis_session import RedisLoginRateLimiter, RedisSessionStore
from knowagent.identity.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAuditSink,
)
from knowagent.identity.ports import SessionRecord
from knowagent.platform.database import transactional_session


@dataclass(frozen=True, slots=True)
class CurrentContext:
    account: Account
    session: SessionRecord
    token: str


def get_database_session(request: Request) -> Generator[Session, None, None]:
    yield from transactional_session(request.app.state.session_factory)


DatabaseSession = Annotated[Session, Depends(get_database_session)]


def get_redis_client(request: Request) -> Redis:  # type: ignore[type-arg]
    return request.app.state.redis_client


RedisClient = Annotated[Redis, Depends(get_redis_client)]  # type: ignore[type-arg]


@lru_cache(maxsize=1)
def get_password_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def build_auth_service(
    request: Request, database: DatabaseSession, redis: RedisClient
) -> AuthService:
    settings = request.app.state.settings
    return AuthService(
        accounts=SqlAlchemyAccountRepository(database),
        passwords=get_password_hasher(),
        sessions=RedisSessionStore(redis, prefix=settings.redis_prefix),
        audit=SqlAlchemyAuditSink(database),
        rate_limiter=RedisLoginRateLimiter(
            redis,
            prefix=settings.redis_prefix,
            attempts=settings.login_attempts,
            window_seconds=settings.login_window_seconds,
        ),
        session_ttl_seconds=settings.session_ttl_seconds,
    )


AuthServiceDependency = Annotated[AuthService, Depends(build_auth_service)]


def get_current_context(
    request: Request,
    auth: AuthServiceDependency,
    session_token: Annotated[str | None, Cookie(alias="knowagent_session")] = None,
) -> CurrentContext:
    cookie_name = request.app.state.settings.session_cookie_name
    token = request.cookies.get(cookie_name, session_token)
    if not token:
        raise AuthenticationError("SESSION_REQUIRED", "请先登录")
    account, record = auth.authenticate_session(token)
    return CurrentContext(account=account, session=record, token=token)


CurrentContextDependency = Annotated[CurrentContext, Depends(get_current_context)]


def require_csrf(
    context: CurrentContextDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> CurrentContext:
    if not csrf_token or not secrets_equal(csrf_token, context.session.csrf_token):
        raise AuthorizationError("CSRF_INVALID", "安全校验失败，请刷新页面后重试")
    return context


CsrfContext = Annotated[CurrentContext, Depends(require_csrf)]


def require_admin(context: CurrentContextDependency, auth: AuthServiceDependency) -> CurrentContext:
    auth.authorize(context.account, allowed_roles={AccountRole.ADMIN})
    return context


AdminContext = Annotated[CurrentContext, Depends(require_admin)]


def require_admin_csrf(context: CsrfContext, auth: AuthServiceDependency) -> CurrentContext:
    auth.authorize(context.account, allowed_roles={AccountRole.ADMIN})
    return context


AdminCsrfContext = Annotated[CurrentContext, Depends(require_admin_csrf)]


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
