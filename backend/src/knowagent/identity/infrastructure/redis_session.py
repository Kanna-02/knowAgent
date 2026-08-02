from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from knowagent.common.errors import DependencyUnavailableError
from knowagent.identity.ports import NewSession, SessionRecord


class RedisSessionStore:
    def __init__(self, client: Redis, *, prefix: str) -> None:  # type: ignore[type-arg]
        self._client = client
        self._prefix = prefix.rstrip(":")

    def create(self, record: SessionRecord) -> NewSession:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        ttl_seconds = max(1, int((record.expires_at - datetime.now(UTC)).total_seconds()))
        stored_record = {
            "account_id": str(record.account_id),
            "session_version": record.session_version,
            "csrf_token": csrf_token,
            "expires_at": record.expires_at.isoformat(),
        }
        key = self._session_key(token)
        account_key = self._account_key(record.account_id)
        try:
            pipeline = self._client.pipeline(transaction=True)
            pipeline.setex(key, ttl_seconds, json.dumps(stored_record, separators=(",", ":")))
            pipeline.sadd(account_key, key)
            pipeline.expire(account_key, ttl_seconds)
            pipeline.execute()
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error
        return NewSession(token=token, csrf_token=csrf_token, expires_at=record.expires_at)

    def get(self, token: str) -> SessionRecord | None:
        try:
            payload = self._client.get(self._session_key(token))
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error
        if payload is None:
            return None
        try:
            data = json.loads(payload)
            return SessionRecord(
                account_id=UUID(data["account_id"]),
                session_version=int(data["session_version"]),
                csrf_token=str(data["csrf_token"]),
                expires_at=datetime.fromisoformat(data["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.delete(token)
            return None

    def delete(self, token: str) -> None:
        key = self._session_key(token)
        try:
            payload = self._client.get(key)
            pipeline = self._client.pipeline(transaction=True)
            pipeline.delete(key)
            if payload is not None:
                data = json.loads(payload)
                pipeline.srem(self._account_key(UUID(data["account_id"])), key)
            pipeline.execute()
        except (RedisError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise DependencyUnavailableError("redis") from error

    def revoke_account(self, account_id: UUID) -> None:
        account_key = self._account_key(account_id)
        try:
            keys = self._client.smembers(account_key)
            pipeline = self._client.pipeline(transaction=True)
            if keys:
                pipeline.delete(*keys)
            pipeline.delete(account_key)
            pipeline.execute()
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error

    def _session_key(self, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{self._prefix}:session:{digest}"

    def _account_key(self, account_id: UUID) -> str:
        return f"{self._prefix}:account:{account_id}:sessions"


class RedisLoginRateLimiter:
    def __init__(
        self,
        client: Redis,  # type: ignore[type-arg]
        *,
        prefix: str,
        attempts: int,
        window_seconds: int,
    ) -> None:
        self._client = client
        self._prefix = prefix.rstrip(":")
        self._attempts = attempts
        self._window_seconds = window_seconds

    def allow(self, username: str, source_ip: str, entry: str) -> bool:
        keys = self._keys(username, source_ip, entry)
        try:
            counts = [int(self._client.get(key) or 0) for key in keys]
            return all(count < self._attempts for count in counts)
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error

    def record_failure(self, username: str, source_ip: str, entry: str) -> None:
        try:
            pipeline = self._client.pipeline(transaction=True)
            for key in self._keys(username, source_ip, entry):
                pipeline.incr(key)
                pipeline.expire(key, self._window_seconds)
            pipeline.execute()
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error

    def reset_account(self, username: str, entry: str) -> None:
        try:
            self._client.delete(self._account_login_key(username, entry))
        except RedisError as error:
            raise DependencyUnavailableError("redis") from error

    def _keys(self, username: str, source_ip: str, entry: str) -> tuple[str, str]:
        return (
            self._account_login_key(username, entry),
            self._ip_login_key(source_ip, entry),
        )

    def _account_login_key(self, username: str, entry: str) -> str:
        account_digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
        return f"{self._prefix}:login:{entry}:account:{account_digest}"

    def _ip_login_key(self, source_ip: str, entry: str) -> str:
        ip_digest = hashlib.sha256(source_ip.encode("utf-8")).hexdigest()[:24]
        return f"{self._prefix}:login:{entry}:ip:{ip_digest}"
