from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from _fakes import FakeRedis
from fastapi.testclient import TestClient

from knowagent.api.app import create_app
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.notifications.domain.models import (
    NotificationDeliveryStatus,
    NotificationEventType,
)
from knowagent.notifications.infrastructure.sqlalchemy_models import NotificationDeliveryRecord
from knowagent.platform.outbox import OutboxEventRecord
from knowagent.platform.settings import Settings

PASSWORD = "Temporary1!"
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'notifications-api.db'}",
        redis_url="redis://unused",
        redis_prefix="test-notifications-api",
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
                _account("notifications.user", AccountRole.USER, password_hash),
                _account("notifications.admin", AccountRole.ADMIN, password_hash),
            ]
        )
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.state.engine.dispose()


def test_notification_configuration_is_admin_only_and_round_trips(client: TestClient) -> None:
    user_session = _login(client, "user", "notifications.user")
    denied = client.put(
        "/api/v1/admin/notification-configuration",
        headers={"X-CSRF-Token": str(user_session["csrf_token"])},
        json=_configuration_payload(),
    )
    assert denied.status_code == 403

    admin_session = _login(client, "admin", "notifications.admin")
    saved = client.put(
        "/api/v1/admin/notification-configuration",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
        json=_configuration_payload(),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["enabled"] is True
    assert saved.json()["secret_reference"] == "KNOWAGENT_NOTIFICATION_TOKEN"
    assert "secret_value" not in saved.json()

    fetched = client.get("/api/v1/admin/notification-configuration")
    assert fetched.status_code == 200
    assert fetched.json() == saved.json()


def test_configuration_rejects_unknown_template_variable(client: TestClient) -> None:
    admin_session = _login(client, "admin", "notifications.admin")
    payload = _configuration_payload()
    payload["ticket_created_template"] = '{"receiver":"${recipient.email}"}'
    response = client.put(
        "/api/v1/admin/notification-configuration",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
        json=payload,
    )
    assert response.status_code == 422


def test_admin_lists_and_retries_permanent_failure(client: TestClient) -> None:
    admin_session = _login(client, "admin", "notifications.admin")
    delivery_id = uuid4()
    outbox_id = uuid4()
    with client.app.state.session_factory.begin() as session:
        session.add(
            OutboxEventRecord(
                id=outbox_id,
                aggregate_type="ticket",
                aggregate_id=uuid4(),
                event_type=NotificationEventType.TICKET_CREATED.value,
                payload={"ticket_id": str(uuid4()), "system_id": str(uuid4())},
                status="PROCESSED",
                idempotency_key=f"api-test:{outbox_id}",
                created_at=NOW,
                processed_at=NOW,
            )
        )
        session.add(
            NotificationDeliveryRecord(
                id=delivery_id,
                outbox_id=outbox_id,
                event_type=NotificationEventType.TICKET_CREATED,
                recipient_address="owner.one",
                status=NotificationDeliveryStatus.PERMANENT_FAILURE,
                idempotency_key=f"api-test:{delivery_id}",
                attempt_count=3,
                cycle_attempt=3,
                last_error_code="PROVIDER_REJECTED",
                last_error_message="notification provider rejected the request",
                created_at=NOW,
                updated_at=NOW,
            )
        )

    listing = client.get(
        "/api/v1/admin/notification-deliveries",
        params={"status": "PERMANENT_FAILURE", "page": 1, "page_size": 20},
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["last_error_code"] == "PROVIDER_REJECTED"

    retried = client.post(
        f"/api/v1/admin/notification-deliveries/{delivery_id}/retry",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "PENDING"
    assert retried.json()["attempt_count"] == 3
    assert retried.json()["cycle_attempt"] == 0

    conflict = client.post(
        f"/api/v1/admin/notification-deliveries/{delivery_id}/retry",
        headers={"X-CSRF-Token": str(admin_session["csrf_token"])},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "NOTIFICATION_NOT_RETRYABLE"


def _configuration_payload() -> dict[str, object]:
    return {
        "enabled": True,
        "endpoint_url": "https://notify.company.internal/api/messages",
        "auth_type": "BEARER",
        "auth_header_name": "Authorization",
        "secret_reference": "KNOWAGENT_NOTIFICATION_TOKEN",
        "ticket_created_template": (
            '{"receiver":"${recipient}","title":"${title}","ticket":"${ticket_id}"}'
        ),
        "ticket_replied_template": (
            '{"receiver":"${recipient}","title":"${title}","content":"${reply_body}"}'
        ),
        "success_status_codes": [200, 201, 202],
        "timeout_seconds": 5,
        "max_attempts": 3,
        "retry_base_seconds": 30,
    }


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
