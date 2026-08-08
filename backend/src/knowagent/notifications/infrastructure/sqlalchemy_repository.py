from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from knowagent.common.errors import ConflictError, NotFoundError
from knowagent.identity.domain.models import AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationConfiguration,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationRecipient,
    NotificationRequest,
    OutboxEvent,
    OutboxStatus,
)
from knowagent.notifications.infrastructure.sqlalchemy_models import (
    NotificationConfigurationRecord,
    NotificationDeliveryRecord,
)
from knowagent.notifications.template import validate_notification_template
from knowagent.platform.outbox import OutboxEventRecord
from knowagent.systems.domain.models import SystemRole
from knowagent.systems.infrastructure.sqlalchemy_models import (
    AccountSystemRoleRecord,
    BusinessSystemRecord,
)

# SQLAlchemy exposes SQL functions dynamically; Pylint cannot infer that call contract.
# pylint: disable=not-callable


class SqlAlchemyNotificationRepository:  # pylint: disable=too-many-public-methods,too-many-arguments
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_configuration(self) -> NotificationConfiguration | None:
        record = self._session.scalar(
            select(NotificationConfigurationRecord).where(
                NotificationConfigurationRecord.name == "default"
            )
        )
        return self._to_configuration(record) if record is not None else None

    def save_configuration(
        self, configuration: NotificationConfiguration
    ) -> NotificationConfiguration:
        validate_notification_template(configuration.ticket_created_template)
        validate_notification_template(configuration.ticket_replied_template)
        self._validate_auth(configuration)
        record = self._session.scalar(
            select(NotificationConfigurationRecord)
            .where(NotificationConfigurationRecord.name == "default")
            .with_for_update()
        )
        if record is None:
            record = NotificationConfigurationRecord(id=configuration.id, name="default")
            self._session.add(record)
        record.enabled = configuration.enabled
        record.endpoint_url = configuration.endpoint_url.strip()
        record.auth_type = configuration.auth_type
        record.auth_header_name = configuration.auth_header_name
        record.secret_reference = configuration.secret_reference
        record.ticket_created_template = configuration.ticket_created_template
        record.ticket_replied_template = configuration.ticket_replied_template
        record.success_status_codes = list(configuration.success_status_codes)
        record.timeout_seconds = configuration.timeout_seconds
        record.max_attempts = configuration.max_attempts
        record.retry_base_seconds = configuration.retry_base_seconds
        record.updated_by = configuration.updated_by
        record.updated_at = configuration.updated_at
        self._session.flush()
        return self._to_configuration(record)

    def list_pending_events(self, *, limit: int) -> list[OutboxEvent]:
        records = self._session.scalars(
            select(OutboxEventRecord)
            .where(
                OutboxEventRecord.status == OutboxStatus.PENDING.value,
                OutboxEventRecord.event_type.in_([event.value for event in NotificationEventType]),
            )
            .order_by(OutboxEventRecord.created_at, OutboxEventRecord.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        return [self._to_outbox(record) for record in records]

    def resolve_recipients(self, event: OutboxEvent) -> tuple[NotificationRecipient, ...]:
        if event.event_type is NotificationEventType.TICKET_CREATED:
            system_id = self._payload_uuid(event.payload, "system_id")
            rows = self._session.execute(
                select(AccountRecord.id, AccountRecord.username)
                .join(
                    AccountSystemRoleRecord,
                    AccountSystemRoleRecord.account_id == AccountRecord.id,
                )
                .where(
                    AccountSystemRoleRecord.system_id == system_id,
                    AccountSystemRoleRecord.role == SystemRole.SYSTEM_OWNER,
                    AccountRecord.status == AccountStatus.ACTIVE,
                )
                .order_by(AccountRecord.username)
            ).all()
            return tuple(
                NotificationRecipient(account_id=row.id, address=row.username) for row in rows
            )
        requester_id = self._payload_uuid(event.payload, "requester_id")
        row = self._session.execute(
            select(AccountRecord.id, AccountRecord.username).where(
                AccountRecord.id == requester_id,
                AccountRecord.status == AccountStatus.ACTIVE,
            )
        ).one_or_none()
        if row is None:
            return ()
        return (NotificationRecipient(account_id=row.id, address=row.username),)

    def add_delivery(
        self,
        *,
        event: OutboxEvent,
        recipient: NotificationRecipient,
        status: NotificationDeliveryStatus,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> NotificationDelivery:  # pylint: disable=too-many-arguments
        recipient_key = str(recipient.account_id or recipient.address)
        record = NotificationDeliveryRecord(
            id=uuid4(),
            outbox_id=event.id,
            event_type=event.event_type,
            recipient_id=recipient.account_id,
            recipient_address=recipient.address,
            status=status,
            idempotency_key=f"{event.idempotency_key}:{recipient_key}",
            attempt_count=0,
            cycle_attempt=0,
            last_error_code=error_code,
            last_error_message=error_message,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_delivery(record)

    def mark_event_processed(self, event_id: UUID, *, now: datetime) -> None:
        record = self._session.get(OutboxEventRecord, event_id)
        if record is None:
            raise NotFoundError("OUTBOX_EVENT_NOT_FOUND", "通知事件不存在")
        record.status = OutboxStatus.PROCESSED.value
        record.processed_at = now
        self._session.flush()

    def list_deliveries(
        self,
        *,
        status: NotificationDeliveryStatus | None,
        event_type: NotificationEventType | None,
        page: int,
        page_size: int,
    ) -> tuple[list[NotificationDelivery], int]:
        filters = []
        if status is not None:
            filters.append(NotificationDeliveryRecord.status == status)
        if event_type is not None:
            filters.append(NotificationDeliveryRecord.event_type == event_type)
        total = int(
            self._session.scalar(select(func.count(NotificationDeliveryRecord.id)).where(*filters))
            or 0
        )
        records = self._session.scalars(
            select(NotificationDeliveryRecord)
            .where(*filters)
            .order_by(NotificationDeliveryRecord.created_at.desc(), NotificationDeliveryRecord.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [self._to_delivery(record) for record in records], total

    def get_delivery(self, delivery_id: UUID) -> NotificationDelivery | None:
        record = self._session.get(NotificationDeliveryRecord, delivery_id)
        return self._to_delivery(record) if record is not None else None

    def claim_delivery(
        self, delivery_id: UUID, *, now: datetime
    ) -> tuple[NotificationDelivery, NotificationConfiguration, NotificationRequest, UUID] | None:
        record = self._session.scalar(
            select(NotificationDeliveryRecord)
            .where(NotificationDeliveryRecord.id == delivery_id)
            .with_for_update()
        )
        if record is None:
            raise NotFoundError("NOTIFICATION_DELIVERY_NOT_FOUND", "通知记录不存在")
        if record.status not in {
            NotificationDeliveryStatus.PENDING,
            NotificationDeliveryStatus.QUEUED,
            NotificationDeliveryStatus.RETRY_SCHEDULED,
        }:
            return None
        next_attempt_at = self._aware(record.next_attempt_at)
        if next_attempt_at is not None and next_attempt_at > now:
            return None
        configuration = self.get_configuration()
        if configuration is None or not configuration.enabled:
            record.status = NotificationDeliveryStatus.SKIPPED
            record.last_error_code = "NOTIFICATION_DISABLED"
            record.last_error_message = "通知配置未启用"
            record.updated_at = now
            self._session.flush()
            return None
        event_record = self._session.get(OutboxEventRecord, record.outbox_id)
        if event_record is None:
            raise NotFoundError("OUTBOX_EVENT_NOT_FOUND", "通知事件不存在")
        event = self._to_outbox(event_record)
        attempt_id = uuid4()
        record.status = NotificationDeliveryStatus.DELIVERING
        record.active_attempt_id = attempt_id
        record.next_attempt_at = None
        record.updated_at = now
        self._session.flush()
        delivery = self._to_delivery(record)
        return delivery, configuration, self._build_request(event, delivery), attempt_id

    def record_success(
        self,
        delivery_id: UUID,
        *,
        attempt_id: UUID,
        status_code: int,
        provider_message_id: str | None,
        response_summary: str | None,
        now: datetime,
    ) -> NotificationDelivery:
        record = self._lock_delivery(delivery_id)
        if not self._attempt_is_active(record, attempt_id):
            return self._to_delivery(record)
        record.status = NotificationDeliveryStatus.DELIVERED
        record.active_attempt_id = None
        record.attempt_count += 1
        record.cycle_attempt += 1
        record.last_status_code = status_code
        record.last_error_code = None
        record.last_error_message = None
        record.provider_message_id = provider_message_id
        record.response_summary = response_summary
        record.delivered_at = now
        record.updated_at = now
        self._session.flush()
        return self._to_delivery(record)

    def record_failure(
        self,
        delivery_id: UUID,
        *,
        attempt_id: UUID,
        error_code: str,
        error_message: str,
        status_code: int | None,
        retryable: bool,
        maximum_attempts: int,
        retry_base_seconds: int,
        now: datetime,
    ) -> NotificationDelivery:  # pylint: disable=too-many-arguments
        record = self._lock_delivery(delivery_id)
        if not self._attempt_is_active(record, attempt_id):
            return self._to_delivery(record)
        record.attempt_count += 1
        record.cycle_attempt += 1
        record.last_status_code = status_code
        record.last_error_code = error_code
        record.last_error_message = error_message[:500]
        record.updated_at = now
        if retryable and record.cycle_attempt < maximum_attempts:
            delay = retry_base_seconds * (2 ** (record.cycle_attempt - 1))
            record.status = NotificationDeliveryStatus.RETRY_SCHEDULED
            record.next_attempt_at = now + timedelta(seconds=delay)
        else:
            record.status = NotificationDeliveryStatus.PERMANENT_FAILURE
            record.next_attempt_at = None
        self._session.flush()
        return self._to_delivery(record)

    def retry_delivery(self, *, delivery_id: UUID, now: datetime) -> NotificationDelivery:
        record = self._lock_delivery(delivery_id)
        if record.status is not NotificationDeliveryStatus.PERMANENT_FAILURE:
            raise ConflictError("NOTIFICATION_NOT_RETRYABLE", "只有永久失败的通知可以人工重试")
        record.status = NotificationDeliveryStatus.PENDING
        record.active_attempt_id = None
        record.cycle_attempt = 0
        record.next_attempt_at = now
        record.last_error_code = None
        record.last_error_message = None
        record.updated_at = now
        self._session.flush()
        return self._to_delivery(record)

    def list_due_delivery_ids(
        self,
        *,
        now: datetime,
        stale_before: datetime,
        limit: int,
    ) -> list[UUID]:
        due = or_(
            NotificationDeliveryRecord.status == NotificationDeliveryStatus.PENDING,
            (
                (NotificationDeliveryRecord.status == NotificationDeliveryStatus.RETRY_SCHEDULED)
                & (NotificationDeliveryRecord.next_attempt_at <= now)
            ),
            (
                NotificationDeliveryRecord.status.in_(
                    [
                        NotificationDeliveryStatus.QUEUED,
                        NotificationDeliveryStatus.DELIVERING,
                    ]
                )
                & (NotificationDeliveryRecord.updated_at <= stale_before)
            ),
        )
        records = self._session.scalars(
            select(NotificationDeliveryRecord)
            .where(due)
            .order_by(NotificationDeliveryRecord.created_at, NotificationDeliveryRecord.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for record in records:
            record.status = NotificationDeliveryStatus.QUEUED
            record.active_attempt_id = None
            record.updated_at = now
        self._session.flush()
        return [record.id for record in records]

    def _build_request(
        self, event: OutboxEvent, delivery: NotificationDelivery
    ) -> NotificationRequest:
        system_id = self._payload_uuid(event.payload, "system_id")
        system_name = self._session.scalar(
            select(BusinessSystemRecord.name).where(BusinessSystemRecord.id == system_id)
        )
        variables = dict(event.payload)
        variables.update(
            {
                "event_id": str(event.id),
                "event_type": event.event_type.value,
                "recipient": delivery.recipient_address,
                "recipient_id": str(delivery.recipient_id or ""),
                "system_name": system_name or "",
                "attempt": delivery.cycle_attempt + 1,
                "active": True,
                "reply_body": str(event.payload.get("reply_body", "")),
            }
        )
        return NotificationRequest(
            event_type=event.event_type,
            recipient=delivery.recipient_address,
            variables=variables,
        )

    def _lock_delivery(self, delivery_id: UUID) -> NotificationDeliveryRecord:
        record = self._session.scalar(
            select(NotificationDeliveryRecord)
            .where(NotificationDeliveryRecord.id == delivery_id)
            .with_for_update()
        )
        if record is None:
            raise NotFoundError("NOTIFICATION_DELIVERY_NOT_FOUND", "通知记录不存在")
        return record

    @staticmethod
    def _attempt_is_active(record: NotificationDeliveryRecord, attempt_id: UUID) -> bool:
        return (
            record.status is NotificationDeliveryStatus.DELIVERING
            and record.active_attempt_id == attempt_id
        )

    @staticmethod
    def _validate_auth(configuration: NotificationConfiguration) -> None:
        if configuration.auth_type is NotificationAuthType.NONE:
            return
        if not configuration.secret_reference or not configuration.secret_reference.strip():
            raise ValueError("notification secret reference is required")
        if not configuration.auth_header_name or not configuration.auth_header_name.strip():
            raise ValueError("notification auth header name is required")

    @staticmethod
    def _payload_uuid(payload: dict[str, object], key: str) -> UUID:
        value = payload.get(key)
        if not isinstance(value, str):
            raise ValueError(f"notification event payload is missing {key}")
        return UUID(value)

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def _to_configuration(
        cls, record: NotificationConfigurationRecord
    ) -> NotificationConfiguration:
        return NotificationConfiguration(
            id=record.id,
            enabled=record.enabled,
            endpoint_url=record.endpoint_url,
            auth_type=record.auth_type,
            auth_header_name=record.auth_header_name,
            secret_reference=record.secret_reference,
            ticket_created_template=record.ticket_created_template,
            ticket_replied_template=record.ticket_replied_template,
            success_status_codes=tuple(record.success_status_codes),
            timeout_seconds=record.timeout_seconds,
            max_attempts=record.max_attempts,
            retry_base_seconds=record.retry_base_seconds,
            updated_by=record.updated_by,
            created_at=cls._aware(record.created_at) or datetime.now(UTC),
            updated_at=cls._aware(record.updated_at) or datetime.now(UTC),
        )

    @classmethod
    def _to_outbox(cls, record: OutboxEventRecord) -> OutboxEvent:
        return OutboxEvent(
            id=record.id,
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            event_type=NotificationEventType(record.event_type),
            payload=record.payload,
            status=OutboxStatus(record.status),
            idempotency_key=record.idempotency_key,
            created_at=cls._aware(record.created_at) or datetime.now(UTC),
            processed_at=cls._aware(record.processed_at),
        )

    @classmethod
    def _to_delivery(cls, record: NotificationDeliveryRecord) -> NotificationDelivery:
        return NotificationDelivery(
            id=record.id,
            outbox_id=record.outbox_id,
            event_type=record.event_type,
            recipient_id=record.recipient_id,
            recipient_address=record.recipient_address,
            status=record.status,
            idempotency_key=record.idempotency_key,
            attempt_count=record.attempt_count,
            cycle_attempt=record.cycle_attempt,
            next_attempt_at=cls._aware(record.next_attempt_at),
            last_status_code=record.last_status_code,
            last_error_code=record.last_error_code,
            last_error_message=record.last_error_message,
            provider_message_id=record.provider_message_id,
            response_summary=record.response_summary,
            delivered_at=cls._aware(record.delivered_at),
            created_at=cls._aware(record.created_at) or datetime.now(UTC),
            updated_at=cls._aware(record.updated_at) or datetime.now(UTC),
        )
