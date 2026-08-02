from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    redis_prefix: str
    session_cookie_name: str
    session_ttl_seconds: int
    cookie_secure: bool
    login_attempts: int
    login_window_seconds: int
    environment: str

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "KNOWAGENT_DATABASE_URL",
                "postgresql+psycopg://knowagent:knowagent@127.0.0.1:5432/knowagent",
            ),
            redis_url=os.getenv("KNOWAGENT_REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_prefix=os.getenv("KNOWAGENT_REDIS_PREFIX", "knowagent"),
            session_cookie_name=os.getenv("KNOWAGENT_SESSION_COOKIE", "knowagent_session"),
            session_ttl_seconds=int(os.getenv("KNOWAGENT_SESSION_TTL_SECONDS", "28800")),
            cookie_secure=_as_bool(os.getenv("KNOWAGENT_COOKIE_SECURE", "true")),
            login_attempts=int(os.getenv("KNOWAGENT_LOGIN_ATTEMPTS", "8")),
            login_window_seconds=int(os.getenv("KNOWAGENT_LOGIN_WINDOW_SECONDS", "900")),
            environment=os.getenv("KNOWAGENT_ENVIRONMENT", "production"),
        )
