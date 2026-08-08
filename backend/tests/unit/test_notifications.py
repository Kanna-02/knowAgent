from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationConfiguration,
    NotificationEventType,
    NotificationRequest,
)
from knowagent.notifications.errors import (
    PermanentNotificationError,
    TransientNotificationError,
)
from knowagent.notifications.infrastructure.http_provider import HttpNotificationProvider
from knowagent.notifications.template import (
    NotificationTemplateError,
    render_notification_template,
    validate_notification_template,
)
from knowagent.platform.outbox import OutboxEventRecord
from knowagent.systems.domain.models import SystemRole
from knowagent.systems.infrastructure.sqlalchemy_models import AccountSystemRoleRecord
from knowagent.tickets.application.workflow import TicketWorkflowService
from knowagent.tickets.domain.models import (
    ReplyAuthorRole,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

CREATED_TEMPLATE = """{
  "receiver": "${recipient}",
  "subject": "工单 ${ticket_id}",
  "content": "${title}"
}"""


def configuration(**overrides: object) -> NotificationConfiguration:
    values: dict[str, object] = {
        "enabled": True,
        "endpoint_url": "https://notify.example.test/messages",
        "auth_type": NotificationAuthType.BEARER,
        "auth_header_name": "Authorization",
        "secret_reference": "KNOWAGENT_TEST_NOTIFY_TOKEN",
        "ticket_created_template": CREATED_TEMPLATE,
        "ticket_replied_template": CREATED_TEMPLATE,
        "success_status_codes": (200, 201, 202),
        "timeout_seconds": 5,
        "max_attempts": 3,
        "retry_base_seconds": 10,
    }
    values.update(overrides)
    return NotificationConfiguration(**values)  # type: ignore[arg-type]


def request() -> NotificationRequest:
    return NotificationRequest(
        event_type=NotificationEventType.TICKET_CREATED,
        recipient="owner.one",
        variables={
            "recipient": "owner.one",
            "ticket_id": "ticket-123",
            "title": "ESB 发布失败",
        },
    )


def test_template_validation_and_rendering_preserve_json_types() -> None:
    validate_notification_template(CREATED_TEMPLATE)
    rendered = render_notification_template(
        '{"receiver":"${recipient}","attempt":${attempt},"active":${active}}',
        {"recipient": "owner.one", "attempt": 2, "active": True},
    )

    assert rendered == {"receiver": "owner.one", "attempt": 2, "active": True}


def test_template_rejects_unknown_placeholders() -> None:
    with pytest.raises(NotificationTemplateError, match="unknown placeholder"):
        validate_notification_template('{"receiver":"${recipient.email}"}')


def test_provider_posts_rendered_json_with_secret_reference_and_idempotency_key() -> None:
    captured: dict[str, object] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured["url"] = str(http_request.url)
        captured["authorization"] = http_request.headers.get("Authorization")
        captured["idempotency"] = http_request.headers.get("Idempotency-Key")
        captured["body"] = http_request.content
        return httpx.Response(202, json={"message_id": "provider-456"})

    provider = HttpNotificationProvider(
        environment={"KNOWAGENT_TEST_NOTIFY_TOKEN": "secret-token"},
        allowed_hosts=("notify.example.test",),
        runtime_environment="production",
        transport=httpx.MockTransport(handler),
    )

    receipt = asyncio.run(
        provider.send(
            configuration=configuration(),
            request=request(),
            idempotency_key="notification-123",
        )
    )

    assert receipt.status_code == 202
    assert receipt.provider_message_id == "provider-456"
    assert captured == {
        "url": "https://notify.example.test/messages",
        "authorization": "Bearer secret-token",
        "idempotency": "notification-123",
        "body": b'{"receiver":"owner.one","subject":"\xe5\xb7\xa5\xe5\x8d\x95 ticket-123","content":"ESB \xe5\x8f\x91\xe5\xb8\x83\xe5\xa4\xb1\xe8\xb4\xa5"}',
    }


@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
def test_provider_classifies_retryable_status_as_transient(status_code: int) -> None:
    provider = _provider_returning(status_code)
    with pytest.raises(TransientNotificationError):
        asyncio.run(
            provider.send(
                configuration=configuration(),
                request=request(),
                idempotency_key="retryable",
            )
        )


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_provider_classifies_other_client_errors_as_permanent(status_code: int) -> None:
    provider = _provider_returning(status_code)
    with pytest.raises(PermanentNotificationError):
        asyncio.run(
            provider.send(
                configuration=configuration(),
                request=request(),
                idempotency_key="permanent",
            )
        )


def test_provider_rejects_missing_secret_reference_value() -> None:
    provider = HttpNotificationProvider(
        environment={},
        allowed_hosts=("notify.example.test",),
        runtime_environment="production",
        transport=httpx.MockTransport(lambda _: httpx.Response(202)),
    )
    with pytest.raises(PermanentNotificationError, match="credential reference"):
        asyncio.run(
            provider.send(
                configuration=configuration(),
                request=request(),
                idempotency_key="missing-secret",
            )
        )


def test_provider_denies_production_endpoint_when_allowlist_is_empty() -> None:
    provider = HttpNotificationProvider(
        environment={"KNOWAGENT_TEST_NOTIFY_TOKEN": "secret-token"},
        allowed_hosts=(),
        runtime_environment="production",
        transport=httpx.MockTransport(lambda _: httpx.Response(202)),
    )
    with pytest.raises(PermanentNotificationError, match="allowlist is empty"):
        asyncio.run(
            provider.send(
                configuration=configuration(),
                request=request(),
                idempotency_key="empty-allowlist",
            )
        )


def _provider_returning(status_code: int) -> HttpNotificationProvider:
    environment: Mapping[str, str] = {"KNOWAGENT_TEST_NOTIFY_TOKEN": "secret-token"}
    return HttpNotificationProvider(
        environment=environment,
        allowed_hosts=("notify.example.test",),
        runtime_environment="production",
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code, text="provider error")),
    )


def test_adding_ticket_writes_transactional_outbox_event() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
    ticket = Ticket(
        id=uuid4(),
        system_id=uuid4(),
        requester_id=uuid4(),
        source_run_id=uuid4(),
        assignee_id=None,
        status=TicketStatus.OPEN,
        priority=TicketPriority.NORMAL,
        title="ESB 发布失败",
        question="为什么发布一直失败？",
        normalized_question="为什么发布一直失败",
        deduplication_key="ticket-dedup",
        occurrence_count=1,
        created_at=now,
        updated_at=now,
    )

    with Session(engine) as session:
        SqlAlchemyTicketRepository(session).add_ticket(ticket)
        event = session.scalar(select(OutboxEventRecord))

        assert event is not None
        assert event.event_type == "ticket_created"
        assert event.aggregate_id == ticket.id
        assert event.idempotency_key == f"ticket:{ticket.id}:created"
        assert event.payload["requester_id"] == str(ticket.requester_id)


def test_only_non_requester_reply_writes_outbox_event() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
    requester_id = uuid4()
    outsider_id = uuid4()
    owner_id = uuid4()
    ticket = Ticket(
        id=uuid4(),
        system_id=uuid4(),
        requester_id=requester_id,
        source_run_id=uuid4(),
        assignee_id=None,
        status=TicketStatus.OPEN,
        priority=TicketPriority.NORMAL,
        title="ESB 发布失败",
        question="为什么发布一直失败？",
        normalized_question="为什么发布一直失败",
        deduplication_key="ticket-dedup",
        occurrence_count=1,
        created_at=now,
        updated_at=now,
    )

    with Session(engine) as session:
        session.add_all(
            [
                AccountRecord(
                    id=outsider_id,
                    username="outsider",
                    display_name="Outsider",
                    password_hash="hash",
                    role=AccountRole.USER,
                    source=AccountSource.ADMIN_CREATED,
                    status=AccountStatus.ACTIVE,
                    must_change_password=False,
                    session_version=1,
                ),
                AccountRecord(
                    id=owner_id,
                    username="owner",
                    display_name="Owner",
                    password_hash="hash",
                    role=AccountRole.SYSTEM_OWNER,
                    source=AccountSource.ADMIN_CREATED,
                    status=AccountStatus.ACTIVE,
                    must_change_password=False,
                    session_version=1,
                ),
                AccountSystemRoleRecord(
                    account_id=owner_id,
                    system_id=ticket.system_id,
                    role=SystemRole.SYSTEM_OWNER,
                ),
            ]
        )
        repository = SqlAlchemyTicketRepository(session)
        repository.add_ticket(ticket)
        workflow = TicketWorkflowService(repository=repository)
        requester_reply, _ = workflow.reply(
            ticket_id=ticket.id,
            author_id=requester_id,
            body="补充日志",
            now=now,
        )
        workflow.reply(
            ticket_id=ticket.id,
            author_id=outsider_id,
            body="我也遇到了这个问题",
            now=now,
        )
        owner_reply, _ = workflow.reply(
            ticket_id=ticket.id,
            author_id=owner_id,
            body="请按新模板发布",
            now=now,
        )
        events = session.scalars(select(OutboxEventRecord)).all()

        assert requester_reply.author_role is ReplyAuthorRole.REQUESTER
        assert owner_reply.author_role is ReplyAuthorRole.REVIEWER
        assert len(events) == 2
        by_type = {event.event_type: event for event in events}
        assert set(by_type) == {"ticket_created", "ticket_replied"}
        assert by_type["ticket_replied"].payload["reply_body"] == "请按新模板发布"
        assert (
            by_type["ticket_replied"].idempotency_key
            == f"ticket:{ticket.id}:reply:{owner_reply.id}"
        )
