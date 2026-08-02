from __future__ import annotations

from collections.abc import Mapping


class KnowAgentError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: Mapping[str, str | int | bool] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = dict(details) if details else None


class ValidationError(KnowAgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=422)


class AuthenticationError(KnowAgentError):
    def __init__(self, code: str = "AUTH_INVALID", message: str = "账号或密码不正确") -> None:
        status_code = 429 if code == "AUTH_RATE_LIMITED" else 401
        super().__init__(code, message, status_code=status_code)


class AuthorizationError(KnowAgentError):
    def __init__(self, code: str = "FORBIDDEN", message: str = "没有执行此操作的权限") -> None:
        super().__init__(code, message, status_code=403)


class ConflictError(KnowAgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)


class NotFoundError(KnowAgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=404)


class FeatureDisabledError(KnowAgentError):
    def __init__(self, feature: str) -> None:
        super().__init__(
            "FEATURE_DISABLED",
            f"{feature} 尚未启用",
            status_code=501,
            details={"feature": feature},
        )


class DependencyUnavailableError(KnowAgentError):
    def __init__(self, dependency: str) -> None:
        super().__init__(
            "AUTH_DEPENDENCY_UNAVAILABLE",
            "认证服务暂时不可用",
            status_code=503,
            details={"dependency": dependency},
        )
