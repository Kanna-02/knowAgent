from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI, Header
from pydantic import BaseModel

from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationConfiguration,
    NotificationEventType,
    NotificationRequest,
)
from knowagent.notifications.infrastructure.http_provider import HttpNotificationProvider


class StubMessage(BaseModel):
    receiver: str
    ticket_id: str


def test_http_provider_contract_against_local_fastapi_stub() -> None:
    app = FastAPI()
    captured: dict[str, str] = {}

    @app.post("/messages", status_code=202)
    def create_message(
        payload: StubMessage,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, str]:
        captured.update(
            receiver=payload.receiver,
            ticket_id=payload.ticket_id,
            idempotency_key=idempotency_key,
        )
        return {"message_id": "stub-message-1"}

    template = '{"receiver":"${recipient}","ticket_id":"${ticket_id}"}'
    provider = HttpNotificationProvider(
        environment={},
        allowed_hosts=("notification-stub",),
        runtime_environment="test",
        transport=httpx.ASGITransport(app=app),
    )
    receipt = asyncio.run(
        provider.send(
            configuration=NotificationConfiguration(
                enabled=True,
                endpoint_url="http://notification-stub/messages",
                auth_type=NotificationAuthType.NONE,
                auth_header_name=None,
                secret_reference=None,
                ticket_created_template=template,
                ticket_replied_template=template,
                success_status_codes=(202,),
                timeout_seconds=5,
                max_attempts=3,
                retry_base_seconds=10,
            ),
            request=NotificationRequest(
                event_type=NotificationEventType.TICKET_CREATED,
                recipient="owner.one",
                variables={"recipient": "owner.one", "ticket_id": "ticket-123"},
            ),
            idempotency_key="ticket:ticket-123:created:owner.one",
        )
    )

    assert receipt.status_code == 202
    assert receipt.provider_message_id == "stub-message-1"
    assert captured == {
        "receiver": "owner.one",
        "ticket_id": "ticket-123",
        "idempotency_key": "ticket:ticket-123:created:owner.one",
    }
