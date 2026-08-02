from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Self
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from knowagent.api.app import create_app
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.platform.settings import Settings


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def setex(self, *args: object) -> Self:
        self.commands.append(("setex", args))
        return self

    def sadd(self, *args: object) -> Self:
        self.commands.append(("sadd", args))
        return self

    def expire(self, *args: object) -> Self:
        self.commands.append(("expire", args))
        return self

    def incr(self, *args: object) -> Self:
        self.commands.append(("incr", args))
        return self

    def delete(self, *args: object) -> Self:
        self.commands.append(("delete", args))
        return self

    def srem(self, *args: object) -> Self:
        self.commands.append(("srem", args))
        return self

    def execute(self) -> list[object]:
        results = [getattr(self.redis, name)(*args) for name, args in self.commands]
        self.commands.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}
        self.sets: dict[str, set[str]] = {}

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        del transaction
        return FakePipeline(self)

    def setex(self, key: object, ttl: object, value: object) -> bool:
        del ttl
        self.values[str(key)] = str(value)
        return True

    def get(self, key: object) -> str | int | None:
        return self.values.get(str(key))

    def delete(self, *keys: object) -> int:
        deleted = 0
        for key in keys:
            text = str(key)
            deleted += int(text in self.values or text in self.sets)
            self.values.pop(text, None)
            self.sets.pop(text, None)
        return deleted

    def sadd(self, key: object, *members: object) -> int:
        target = self.sets.setdefault(str(key), set())
        before = len(target)
        target.update(str(member) for member in members)
        return len(target) - before

    def srem(self, key: object, *members: object) -> int:
        target = self.sets.setdefault(str(key), set())
        before = len(target)
        target.difference_update(str(member) for member in members)
        return before - len(target)

    def smembers(self, key: object) -> set[str]:
        return set(self.sets.get(str(key), set()))

    def expire(self, key: object, ttl: object) -> bool:
        del ttl
        return str(key) in self.values or str(key) in self.sets

    def incr(self, key: object) -> int:
        text = str(key)
        value = int(self.values.get(text, 0)) + 1
        self.values[text] = value
        return value


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'identity.db'}",
        redis_url="redis://unused",
        redis_prefix="test",
        session_cookie_name="knowagent_session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="test",
    )
    app = create_app(settings)
    app.state.redis_client = FakeRedis()
    Base.metadata.create_all(app.state.engine)
    password_hash = Argon2PasswordHasher().hash("Temporary1!")
    with app.state.session_factory.begin() as session:
        session.add_all(
            [
                _account("alice", AccountRole.USER, password_hash, must_change=True),
                _account("owner", AccountRole.SYSTEM_OWNER, password_hash, must_change=False),
                _account("admin", AccountRole.ADMIN, password_hash, must_change=False),
                _account(
                    "disabled",
                    AccountRole.USER,
                    password_hash,
                    must_change=False,
                    status=AccountStatus.DISABLED,
                ),
            ]
        )
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.state.engine.dispose()


def _account(
    username: str,
    role: AccountRole,
    password_hash: str,
    *,
    must_change: bool,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> AccountRecord:
    return AccountRecord(
        id=uuid4(),
        username=username,
        display_name=username.title(),
        password_hash=password_hash,
        role=role,
        source=AccountSource.LOCAL_IMPORT,
        status=status,
        must_change_password=must_change,
        session_version=1,
    )


def _login(client: TestClient, entry: str, username: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/auth/{entry}/sessions",
        json={"username": username, "password": "Temporary1!"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_entries_disabled_accounts_and_error_shape(client: TestClient) -> None:
    wrong_entry = client.post(
        "/api/v1/auth/admin/sessions",
        json={"username": "alice", "password": "Temporary1!"},
    )
    disabled = client.post(
        "/api/v1/auth/user/sessions",
        json={"username": "disabled", "password": "Temporary1!"},
    )

    assert wrong_entry.status_code == disabled.status_code == 401
    assert wrong_entry.json()["code"] == disabled.json()["code"] == "AUTH_INVALID"
    assert wrong_entry.json()["message"] == disabled.json()["message"]
    assert wrong_entry.json()["request_id"]


def test_successful_logins_do_not_consume_failure_limit(client: TestClient) -> None:
    for _ in range(6):
        response = client.post(
            "/api/v1/auth/user/sessions",
            json={"username": "owner", "password": "Temporary1!"},
        )

        assert response.status_code == 200, response.text


def test_failed_logins_reach_configured_limit(client: TestClient) -> None:
    for _ in range(4):
        response = client.post(
            "/api/v1/auth/user/sessions",
            json={"username": "owner", "password": "WrongPassword2@"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/v1/auth/user/sessions",
        json={"username": "owner", "password": "Temporary1!"},
    )

    assert limited.status_code == 429
    assert limited.json()["code"] == "AUTH_RATE_LIMITED"


def test_oversized_request_id_is_replaced_before_audit_write(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/user/sessions",
        headers={"X-Request-ID": "x" * 65},
        json={"username": "missing", "password": "Temporary1!"},
    )

    assert response.status_code == 401
    assert response.json()["request_id"] != "x" * 65
    assert len(response.json()["request_id"]) <= 64


def test_first_password_change_requires_csrf_and_rotates_session(client: TestClient) -> None:
    session = _login(client, "user", "alice")
    assert session["must_change_password"] is True

    blocked = client.get("/api/v1/admin/accounts")
    missing_csrf = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "Temporary1!", "new_password": "Replacement2@"},
    )
    changed = client.post(
        "/api/v1/auth/password/change",
        headers={"X-CSRF-Token": str(session["csrf_token"])},
        json={"current_password": "Temporary1!", "new_password": "Replacement2@"},
    )
    current = client.get("/api/v1/auth/me")

    assert blocked.status_code == 403
    assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"
    assert changed.status_code == 204
    assert changed.headers["x-csrf-token"]
    assert current.json()["must_change_password"] is False


def test_admin_can_create_list_and_disable_account_but_not_last_admin(client: TestClient) -> None:
    session = _login(client, "admin", "admin")
    csrf = str(session["csrf_token"])
    created = client.post(
        "/api/v1/admin/accounts",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "second.admin",
            "display_name": "Second Admin",
            "temporary_password": "Temporary22@",
        },
    )
    listed = client.get("/api/v1/admin/accounts", params={"role": "ADMIN", "page_size": 10})
    created_id = created.json()["id"]
    disabled = client.patch(
        f"/api/v1/admin/accounts/{created_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "DISABLED"},
    )
    original_id = next(item["id"] for item in listed.json()["items"] if item["username"] == "admin")
    last_admin = client.patch(
        f"/api/v1/admin/accounts/{original_id}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "DISABLED"},
    )

    assert created.status_code == 201
    assert created.json()["role"] == "ADMIN"
    assert created.json()["must_change_password"] is True
    assert listed.json()["total"] == 2
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert last_admin.status_code == 409
    assert last_admin.json()["code"] == "LAST_ADMIN"


def test_user_cannot_call_admin_api_and_sso_boundary_is_explicit(client: TestClient) -> None:
    _login(client, "user", "owner")
    forbidden = client.get("/api/v1/admin/accounts")
    sso = client.get("/api/v1/auth/sso/company/start", params={"redirect_uri": "/app"})

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert sso.status_code == 501
    assert sso.json()["code"] == "FEATURE_DISABLED"


def test_logout_revokes_server_session(client: TestClient) -> None:
    session = _login(client, "user", "owner")
    logged_out = client.delete(
        "/api/v1/auth/session", headers={"X-CSRF-Token": str(session["csrf_token"])}
    )
    current = client.get("/api/v1/auth/me")

    assert logged_out.status_code == 204
    assert current.status_code == 401
