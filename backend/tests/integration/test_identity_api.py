from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Self
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from knowagent.api.app import create_app
from knowagent.documents.domain.ingestion import DocumentVersionStatus
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


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0

    def put(
        self,
        *,
        key: str,
        content: BytesIO,
        content_type: str,
        content_length: int,
    ) -> None:
        del content_type
        payload = content.read()
        assert len(payload) == content_length
        self.objects[key] = payload
        self.put_calls += 1

    def get(self, *, key: str) -> bytes:
        return self.objects[key]

    def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


class FakeDispatcher:
    def __init__(self) -> None:
        self.jobs: list[UUID] = []

    def enqueue(self, job_id: UUID) -> str:
        self.jobs.append(job_id)
        return f"task-{job_id}"


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
    app.state.object_store = FakeObjectStore()
    app.state.ingestion_dispatcher = FakeDispatcher()
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
    searched = client.get("/api/v1/admin/accounts", params={"role": "ADMIN", "search": "second"})
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
    assert [item["username"] for item in searched.json()["items"]] == ["second.admin"]
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


def test_admin_manages_systems_and_owner_assignments(client: TestClient) -> None:
    session = _login(client, "admin", "admin")
    csrf = str(session["csrf_token"])
    created_esb = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": csrf},
        json={"code": "esb", "name": "企业服务总线", "description": "集成服务"},
    )
    created_crm = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": csrf},
        json={"code": "crm", "name": "客户关系管理", "description": None},
    )
    duplicate = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": csrf},
        json={"code": "ESB", "name": "重复系统"},
    )
    owner_accounts = client.get(
        "/api/v1/admin/accounts", params={"role": "SYSTEM_OWNER", "page_size": 100}
    )
    owner_id = owner_accounts.json()["items"][0]["id"]
    owners = client.put(
        f"/api/v1/admin/systems/{created_esb.json()['id']}/owners",
        headers={"X-CSRF-Token": csrf},
        json={"account_ids": [owner_id], "replace_existing": True},
    )
    disabled = client.patch(
        f"/api/v1/admin/systems/{created_crm.json()['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"status": "DISABLED"},
    )
    admin_page = client.get("/api/v1/admin/systems", params={"page": 1, "page_size": 1})
    admin_list = client.get("/api/v1/systems")

    assert created_esb.status_code == created_crm.status_code == 201
    assert created_esb.json()["code"] == "ESB"
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "SYSTEM_EXISTS"
    assert owners.status_code == 200
    assert owners.json()[0]["account_id"] == owner_id
    assert disabled.json()["status"] == "DISABLED"
    assert admin_page.status_code == 200
    assert admin_page.json()["total"] == 2
    assert len(admin_page.json()["items"]) == 1
    assert {item["code"] for item in admin_list.json()} == {"ESB", "CRM"}

    owner_session = _login(client, "user", "owner")
    assert owner_session["user"]["system_roles"] == [
        {"system_id": created_esb.json()["id"], "role": "SYSTEM_OWNER"}
    ]
    owner_list = client.get("/api/v1/systems")
    assert [item["code"] for item in owner_list.json()] == ["ESB"]
    assert owner_list.json()[0]["owners"] == []


def test_owner_assignment_changes_revoke_existing_owner_sessions(client: TestClient) -> None:
    admin_session = _login(client, "admin", "admin")
    csrf = str(admin_session["csrf_token"])
    created = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": csrf},
        json={"code": "ESB", "name": "企业服务总线"},
    )
    owner_id = client.get("/api/v1/admin/accounts", params={"role": "SYSTEM_OWNER"}).json()[
        "items"
    ][0]["id"]

    _login(client, "user", "owner")
    session_before_assignment = client.cookies.get(
        "knowagent_session", domain="testserver.local", path="/"
    )
    admin_session = _login(client, "admin", "admin")
    assigned = client.put(
        f"/api/v1/admin/systems/{created.json()['id']}/owners",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
        json={"account_ids": [owner_id], "replace_existing": True},
    )
    client.cookies.set(
        "knowagent_session", session_before_assignment, domain="testserver.local", path="/"
    )
    after_assignment = client.get("/api/v1/auth/me")

    _login(client, "user", "owner")
    session_before_removal = client.cookies.get(
        "knowagent_session", domain="testserver.local", path="/"
    )
    admin_session = _login(client, "admin", "admin")
    removed = client.put(
        f"/api/v1/admin/systems/{created.json()['id']}/owners",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
        json={"account_ids": [], "replace_existing": True},
    )
    client.cookies.set(
        "knowagent_session", session_before_removal, domain="testserver.local", path="/"
    )
    after_removal = client.get("/api/v1/auth/me")

    assert assigned.status_code == 200
    assert removed.status_code == 200
    assert after_assignment.status_code == 401
    assert after_removal.status_code == 401


def test_system_mutations_enforce_csrf_rbac_and_owner_role(client: TestClient) -> None:
    admin_session = _login(client, "admin", "admin")
    csrf = str(admin_session["csrf_token"])
    created = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": csrf},
        json={"code": "ESB", "name": "企业服务总线"},
    )
    accounts = client.get("/api/v1/admin/accounts", params={"page_size": 100}).json()["items"]
    user_id = next(item["id"] for item in accounts if item["username"] == "alice")
    invalid_owner = client.put(
        f"/api/v1/admin/systems/{created.json()['id']}/owners",
        headers={"X-CSRF-Token": csrf},
        json={"account_ids": [user_id], "replace_existing": True},
    )
    missing_csrf = client.patch(
        f"/api/v1/admin/systems/{created.json()['id']}", json={"name": "新名称"}
    )

    owner_session = _login(client, "user", "owner")
    forbidden = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": str(owner_session["csrf_token"])},
        json={"code": "CRM", "name": "客户关系管理"},
    )

    assert invalid_owner.status_code == 422
    assert invalid_owner.json()["code"] == "SYSTEM_OWNER_INVALID"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


def test_owner_upload_is_idempotent_queryable_and_failed_job_can_be_retried(
    client: TestClient,
) -> None:
    admin_session = _login(client, "admin", "admin")
    admin_csrf = str(admin_session["csrf_token"])
    system = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": admin_csrf},
        json={"code": "DOCS", "name": "文档系统"},
    ).json()
    other_system = client.post(
        "/api/v1/admin/systems",
        headers={"X-CSRF-Token": admin_csrf},
        json={"code": "OTHER", "name": "其他系统"},
    ).json()
    owner_id = client.get("/api/v1/admin/accounts", params={"role": "SYSTEM_OWNER"}).json()[
        "items"
    ][0]["id"]
    client.put(
        f"/api/v1/admin/systems/{system['id']}/owners",
        headers={"X-CSRF-Token": admin_csrf},
        json={"account_ids": [owner_id], "replace_existing": True},
    )
    owner_session = _login(client, "user", "owner")
    headers = {
        "X-CSRF-Token": str(owner_session["csrf_token"]),
        "Idempotency-Key": "docs-upload-001",
    }
    file_content = b"# Guide\n\nStable content\n"

    first = client.post(
        f"/api/v1/systems/{system['id']}/documents",
        headers=headers,
        data={"document_name": "Guide"},
        files={"file": ("guide.md", file_content, "text/markdown")},
    )
    duplicate = client.post(
        f"/api/v1/systems/{system['id']}/documents",
        headers=headers,
        data={"document_name": "Guide"},
        files={"file": ("guide.md", file_content, "text/markdown")},
    )
    forbidden = client.post(
        f"/api/v1/systems/{other_system['id']}/documents",
        headers={**headers, "Idempotency-Key": "docs-upload-002"},
        data={"document_name": "Other"},
        files={"file": ("other.md", file_content, "text/markdown")},
    )
    admin_session = _login(client, "admin", "admin")
    scoped_idempotency = client.post(
        f"/api/v1/systems/{other_system['id']}/documents",
        headers={
            "X-CSRF-Token": str(admin_session["csrf_token"]),
            "Idempotency-Key": "docs-upload-001",
        },
        data={"document_name": "Other"},
        files={"file": ("other.md", file_content, "text/markdown")},
    )

    assert first.status_code == duplicate.status_code == 202
    assert duplicate.json()["job_id"] == first.json()["job_id"]
    assert duplicate.json()["document_version_id"] == first.json()["document_version_id"]
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "SYSTEM_ACCESS_DENIED"
    assert scoped_idempotency.status_code == 202
    assert scoped_idempotency.json()["job_id"] != first.json()["job_id"]
    assert client.app.state.object_store.put_calls == 2
    assert client.app.state.ingestion_dispatcher.jobs == [
        UUID(first.json()["job_id"]),
        UUID(scoped_idempotency.json()["job_id"]),
    ]

    owner_session = _login(client, "user", "owner")

    status_response = client.get(f"/api/v1/ingestion-jobs/{first.json()['job_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "QUEUED"
    assert status_response.json()["stage"] == "STORED"
    assert status_response.json()["progress"] == 0
    assert status_response.json()["celery_task_id"].startswith("task-")

    invalid_retry = client.post(
        f"/api/v1/ingestion-jobs/{first.json()['job_id']}/retry",
        headers={"X-CSRF-Token": str(owner_session["csrf_token"])},
    )
    assert invalid_retry.status_code == 409
    assert invalid_retry.json()["code"] == "INGESTION_JOB_NOT_RETRYABLE"

    job_id = UUID(first.json()["job_id"])
    claimed = client.app.state.ingestion_coordinator.claim(
        job_id,
        owner="test-worker",
        now=datetime.now(UTC),
        lease_seconds=60,
    )
    assert claimed is not None
    client.app.state.ingestion_coordinator.fail(
        job_id,
        owner="test-worker",
        attempt=claimed.job.attempt,
        error_code="INVALID_FILE",
        error_message="文件无效",
        retryable=False,
        version_status=DocumentVersionStatus.FAILED,
        now=datetime.now(UTC),
        retry_base_seconds=1,
    )
    retry = client.post(
        f"/api/v1/ingestion-jobs/{job_id}/retry",
        headers={"X-CSRF-Token": str(owner_session["csrf_token"])},
    )

    assert retry.status_code == 202
    assert retry.json()["status"] == "QUEUED"
    assert retry.json()["attempt"] == 0
    assert client.app.state.ingestion_dispatcher.jobs == [
        job_id,
        UUID(scoped_idempotency.json()["job_id"]),
        job_id,
    ]
