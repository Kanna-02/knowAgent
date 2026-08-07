from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from _fakes import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import select

from knowagent.api.app import create_app
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import (
    AccountRecord,
    AuditLogRecord,
    Base,
)
from knowagent.platform.settings import Settings
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord

PASSWORD = "Temporary1!"


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'phase3-config.db'}",
        redis_url="redis://unused",
        redis_prefix="test-phase3-config",
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
    password_hash = Argon2PasswordHasher().hash(PASSWORD)
    with app.state.session_factory.begin() as session:
        session.add_all(
            [
                _account("phase3.user.one", AccountRole.USER, password_hash),
                _account("phase3.user.two", AccountRole.USER, password_hash),
                _account("phase3.admin", AccountRole.ADMIN, password_hash),
                BusinessSystemRecord(
                    id=uuid4(),
                    code="PHASE3CFG",
                    name="Phase 3 Configuration",
                    description="Phase 3 API tests",
                    status=BusinessSystemStatus.ACTIVE,
                ),
            ]
        )
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.state.engine.dispose()


def _account(username: str, role: AccountRole, password_hash: str) -> AccountRecord:
    return AccountRecord(
        id=uuid4(),
        username=username,
        display_name=username,
        password_hash=password_hash,
        role=role,
        source=AccountSource.ADMIN_CREATED,
        status=AccountStatus.ACTIVE,
        must_change_password=False,
        session_version=1,
    )


def _login(client: TestClient, entry: str, username: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/auth/{entry}/sessions",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _system_id(client: TestClient) -> str:
    with client.app.state.session_factory() as session:
        system_id = session.scalar(
            select(BusinessSystemRecord.id).where(BusinessSystemRecord.code == "PHASE3CFG")
        )
        assert system_id is not None
        return str(system_id)


def test_conversation_crud_is_scoped_to_creator(client: TestClient) -> None:
    system_id = _system_id(client)
    first_session = _login(client, "user", "phase3.user.one")
    created = client.post(
        "/api/v1/conversations",
        headers={"X-CSRF-Token": str(first_session["csrf_token"])},
        json={"system_id": system_id, "title": "ESB 发布排错"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    own_list = client.get("/api/v1/conversations", params={"system_id": system_id})
    assert own_list.status_code == 200
    assert own_list.json()["total"] == 1
    assert own_list.json()["items"][0]["id"] == conversation_id

    second_session = _login(client, "user", "phase3.user.two")
    foreign_detail = client.get(f"/api/v1/conversations/{conversation_id}")
    assert foreign_detail.status_code == 404
    foreign_list = client.get("/api/v1/conversations", params={"system_id": system_id})
    assert foreign_list.status_code == 200
    assert foreign_list.json()["total"] == 0
    foreign_delete = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers={"X-CSRF-Token": str(second_session["csrf_token"])},
    )
    assert foreign_delete.status_code == 404

    first_session = _login(client, "user", "phase3.user.one")
    deleted = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers={"X-CSRF-Token": str(first_session["csrf_token"])},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404


def test_admin_can_create_activate_and_list_prompt_versions(client: TestClient) -> None:
    user_session = _login(client, "user", "phase3.user.one")
    denied = client.post(
        "/api/v1/admin/prompt-definitions",
        headers={"X-CSRF-Token": str(user_session["csrf_token"])},
        json={
            "scenario": "grounded_answer",
            "version": "grounded-answer-v2",
            "content": "只使用证据回答。",
            "change_note": "test prompt",
        },
    )
    assert denied.status_code == 403

    admin_session = _login(client, "admin", "phase3.admin")
    headers = {"X-CSRF-Token": str(admin_session["csrf_token"])}
    created = client.post(
        "/api/v1/admin/prompt-definitions",
        headers=headers,
        json={
            "scenario": "grounded_answer",
            "version": "grounded-answer-v2",
            "content": "只使用证据回答。",
            "change_note": "test prompt",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["enabled"] is False
    duplicate = client.post(
        "/api/v1/admin/prompt-definitions",
        headers=headers,
        json={
            "scenario": "grounded_answer",
            "version": "grounded-answer-v2",
            "content": "重复版本。",
            "change_note": "duplicate",
        },
    )
    assert duplicate.status_code == 409
    activated = client.post(
        "/api/v1/admin/prompt-definitions/activate",
        headers=headers,
        json={"scenario": "grounded_answer", "version": "grounded-answer-v2"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["enabled"] is True
    listing = client.get(
        "/api/v1/admin/prompt-definitions",
        params={"scenario": "grounded_answer"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_admin_can_create_activate_and_list_retrieval_profiles(client: TestClient) -> None:
    admin_session = _login(client, "admin", "phase3.admin")
    headers = {"X-CSRF-Token": str(admin_session["csrf_token"])}
    payload = {
        "name": "default",
        "version": "profile-v2",
        "keyword_top_k": 24,
        "vector_top_k": 24,
        "result_top_k": 10,
        "rrf_k": 60,
        "keyword_weight": 1.2,
        "vector_weight": 1.0,
        "rerank_candidate_top_k": 20,
        "rerank_top_k": 10,
        "evidence_max_items": 6,
        "evidence_max_characters": 12000,
        "change_note": "raise keyword recall",
    }
    created = client.post(
        "/api/v1/admin/retrieval-profiles",
        headers=headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is False
    activated = client.post(
        "/api/v1/admin/retrieval-profiles/activate",
        headers=headers,
        json={"name": "default", "version": "profile-v2"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True
    listing = client.get(
        "/api/v1/admin/retrieval-profiles",
        params={"name": "default"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    invalid = dict(payload)
    invalid["version"] = "profile-invalid"
    invalid["rerank_top_k"] = 5
    invalid_response = client.post(
        "/api/v1/admin/retrieval-profiles",
        headers=headers,
        json=invalid,
    )
    assert invalid_response.status_code == 422

    with client.app.state.session_factory() as session:
        actions = set(session.scalars(select(AuditLogRecord.action)).all())
    assert "prompt.create" not in actions
    assert {"retrieval_profile.create", "retrieval_profile.activate"}.issubset(actions)
