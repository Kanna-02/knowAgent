from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.notifications.application.delivery import (
    NotificationDeliveryProcessor,
    NotificationPreparationService,
)
from knowagent.notifications.domain.models import (
    DeliveryReceipt,
    NotificationAuthType,
    NotificationConfiguration,
    NotificationDeliveryStatus,
)
from knowagent.notifications.errors import TransientNotificationError
from knowagent.notifications.infrastructure.sqlalchemy_models import NotificationDeliveryRecord
from knowagent.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from knowagent.platform.settings import NotificationRuntimeSettings
from knowagent.systems.domain.models import BusinessSystemStatus, SystemRole
from knowagent.systems.infrastructure.sqlalchemy_models import (
    AccountSystemRoleRecord,
    BusinessSystemRecord,
)
from knowagent.tickets.domain.models import Ticket, TicketPriority, TicketStatus
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

NOW = datetime(2026, 8, 8, 11, 0, tzinfo=UTC)


class FakeProvider:
    def __init__(self, outcomes: list[DeliveryReceipt | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def send(self, *, configuration, request, idempotency_key):  # type: ignore[no-untyped-def]
        del configuration, request
        self.calls.append(idempotency_key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def setup_database() -> tuple[sessionmaker[Session], dict[str, object]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid4()
    requester_id = uuid4()
    system_id = uuid4()
    ticket_id = uuid4()
    with factory.begin() as session:
        session.add_all(
            [
                _account(owner_id, "owner.one", AccountRole.SYSTEM_OWNER),
                _account(requester_id, "requester.one", AccountRole.USER),
                BusinessSystemRecord(
                    id=system_id,
                    code="ESB",
                    name="企业服务总线",
                    description="test",
                    status=BusinessSystemStatus.ACTIVE,
                ),
                AccountSystemRoleRecord(
                    account_id=owner_id,
                    system_id=system_id,
                    role=SystemRole.SYSTEM_OWNER,
                ),
            ]
        )
        SqlAlchemyTicketRepository(session).add_ticket(
            Ticket(
                id=ticket_id,
                system_id=system_id,
                requester_id=requester_id,
                source_run_id=uuid4(),
                assignee_id=None,
                status=TicketStatus.OPEN,
                priority=TicketPriority.NORMAL,
                title="ESB 发布失败",
                question="为什么发布一直失败？",
                normalized_question="为什么发布一直失败",
                deduplication_key="delivery-test",
                occurrence_count=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        SqlAlchemyNotificationRepository(session).save_configuration(_configuration())
    return factory, {
        "owner_id": owner_id,
        "requester_id": requester_id,
        "system_id": system_id,
        "ticket_id": ticket_id,
    }


def test_prepare_ticket_created_event_creates_owner_delivery_once() -> None:
    factory, ids = setup_database()
    with factory.begin() as session:
        prepared = NotificationPreparationService(
            repository=SqlAlchemyNotificationRepository(session)
        ).prepare_pending(now=NOW, limit=100)

    with factory() as session:
        repository = SqlAlchemyNotificationRepository(session)
        deliveries, total = repository.list_deliveries(
            status=None, event_type=None, page=1, page_size=20
        )
        assert prepared == 1
        assert total == 1
        assert deliveries[0].recipient_id == ids["owner_id"]
        assert deliveries[0].recipient_address == "owner.one"
        assert deliveries[0].status is NotificationDeliveryStatus.PENDING

    with factory.begin() as session:
        prepared_again = NotificationPreparationService(
            repository=SqlAlchemyNotificationRepository(session)
        ).prepare_pending(now=NOW, limit=100)
    assert prepared_again == 0


def test_transient_failure_schedules_retry_then_success_preserves_attempt_count() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)
    provider = FakeProvider(
        [
            TransientNotificationError("PROVIDER_UNAVAILABLE", "temporary"),
            DeliveryReceipt(202, "provider-1", "accepted"),
        ]
    )
    completion_times = iter((NOW, NOW + timedelta(seconds=10)))
    processor = NotificationDeliveryProcessor(
        session_factory=factory,
        provider=provider,
        clock=lambda: next(completion_times),
    )

    first = asyncio.run(processor.deliver(delivery_id=delivery_id, now=NOW))
    assert first.status is NotificationDeliveryStatus.RETRY_SCHEDULED
    assert first.attempt_count == 1
    assert first.cycle_attempt == 1
    assert first.next_attempt_at == NOW + timedelta(seconds=10)

    second = asyncio.run(
        processor.deliver(delivery_id=delivery_id, now=NOW + timedelta(seconds=10))
    )
    assert second.status is NotificationDeliveryStatus.DELIVERED
    assert second.attempt_count == 2
    assert second.cycle_attempt == 2
    assert second.provider_message_id == "provider-1"
    assert provider.calls == [first.idempotency_key, first.idempotency_key]


def test_max_attempts_becomes_permanent_and_manual_retry_starts_new_cycle() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)
    failures: list[DeliveryReceipt | Exception] = [
        TransientNotificationError("PROVIDER_UNAVAILABLE", "temporary") for _ in range(4)
    ]
    processor = NotificationDeliveryProcessor(
        session_factory=factory,
        provider=FakeProvider(failures),
        clock=iter(NOW + timedelta(seconds=10 * (2**attempt - 1)) for attempt in range(3)).__next__,
    )

    result = None
    for attempt in range(3):
        result = asyncio.run(
            processor.deliver(
                delivery_id=delivery_id,
                now=NOW + timedelta(seconds=10 * (2**attempt - 1)),
            )
        )
    assert result is not None
    assert result.status is NotificationDeliveryStatus.PERMANENT_FAILURE
    assert result.attempt_count == 3

    with factory.begin() as session:
        retried = SqlAlchemyNotificationRepository(session).retry_delivery(
            delivery_id=delivery_id,
            now=NOW + timedelta(minutes=5),
        )
        assert retried.status is NotificationDeliveryStatus.PENDING
        assert retried.attempt_count == 3
        assert retried.cycle_attempt == 0


def test_delivering_notification_cannot_be_claimed_twice() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)

    with factory.begin() as session:
        first = SqlAlchemyNotificationRepository(session).claim_delivery(delivery_id, now=NOW)
    with factory.begin() as session:
        second = SqlAlchemyNotificationRepository(session).claim_delivery(delivery_id, now=NOW)

    assert first is not None
    assert second is None


def test_stale_attempt_result_cannot_overwrite_newer_success() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)
    repository: SqlAlchemyNotificationRepository

    with factory.begin() as session:
        first = SqlAlchemyNotificationRepository(session).claim_delivery(delivery_id, now=NOW)
        assert first is not None
        first_attempt_id = first[3]
    recovered_at = NOW + timedelta(minutes=3)
    with factory.begin() as session:
        repository = SqlAlchemyNotificationRepository(session)
        assert repository.list_due_delivery_ids(
            now=recovered_at,
            stale_before=recovered_at - timedelta(seconds=1),
            limit=100,
        ) == [delivery_id]
    with factory.begin() as session:
        second = SqlAlchemyNotificationRepository(session).claim_delivery(
            delivery_id, now=recovered_at
        )
        assert second is not None
        second_attempt_id = second[3]
    with factory.begin() as session:
        delivered = SqlAlchemyNotificationRepository(session).record_success(
            delivery_id,
            attempt_id=second_attempt_id,
            status_code=202,
            provider_message_id="provider-new",
            response_summary="accepted",
            now=recovered_at,
        )
    with factory.begin() as session:
        unchanged = SqlAlchemyNotificationRepository(session).record_failure(
            delivery_id,
            attempt_id=first_attempt_id,
            error_code="PROVIDER_UNAVAILABLE",
            error_message="late failure",
            status_code=503,
            retryable=True,
            maximum_attempts=3,
            retry_base_seconds=10,
            now=recovered_at + timedelta(seconds=1),
        )

    assert delivered.status is NotificationDeliveryStatus.DELIVERED
    assert unchanged.status is NotificationDeliveryStatus.DELIVERED
    assert unchanged.attempt_count == 1
    assert unchanged.provider_message_id == "provider-new"


def test_retry_backoff_starts_when_provider_call_finishes() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)
    completed_at = NOW + timedelta(minutes=2)
    processor = NotificationDeliveryProcessor(
        session_factory=factory,
        provider=FakeProvider([TransientNotificationError("PROVIDER_UNAVAILABLE", "temporary")]),
        clock=lambda: completed_at,
    )

    result = asyncio.run(processor.deliver(delivery_id=delivery_id, now=NOW))

    assert result.updated_at == completed_at
    assert result.next_attempt_at == completed_at + timedelta(seconds=10)


def test_notification_recovery_threshold_exceeds_maximum_provider_timeout() -> None:
    with pytest.raises(ValueError, match="must exceed 120 seconds"):
        NotificationRuntimeSettings(dispatch_stale_seconds=120)


def _prepare_one(factory: sessionmaker[Session]) -> UUID:
    with factory.begin() as session:
        repository = SqlAlchemyNotificationRepository(session)
        NotificationPreparationService(repository=repository).prepare_pending(now=NOW, limit=100)
        deliveries, _ = repository.list_deliveries(
            status=None, event_type=None, page=1, page_size=20
        )
        return deliveries[0].id


def _configuration() -> NotificationConfiguration:
    template = '{"receiver":"${recipient}","ticket_id":"${ticket_id}"}'
    return NotificationConfiguration(
        enabled=True,
        endpoint_url="https://notify.example.test/messages",
        auth_type=NotificationAuthType.NONE,
        auth_header_name=None,
        secret_reference=None,
        ticket_created_template=template,
        ticket_replied_template=template,
        success_status_codes=(200, 202),
        timeout_seconds=5,
        max_attempts=3,
        retry_base_seconds=10,
    )


def _account(account_id: UUID, username: str, role: AccountRole) -> AccountRecord:
    return AccountRecord(
        id=account_id,
        username=username,
        display_name=username,
        password_hash="hash",
        role=role,
        source=AccountSource.ADMIN_CREATED,
        status=AccountStatus.ACTIVE,
        must_change_password=False,
        session_version=1,
    )


def test_notification_delivery_status_enum_persists_values() -> None:
    factory, _ = setup_database()
    delivery_id = _prepare_one(factory)
    with factory() as session:
        record = session.get(NotificationDeliveryRecord, delivery_id)
        assert record is not None
        assert record.status is NotificationDeliveryStatus.PENDING
