from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class NotificationAuthType(StrEnum):
    NONE = "NONE"
    BEARER = "BEARER"
    HEADER = "HEADER"


class NotificationEventType(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_REPLIED = "ticket_replied"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    DELIVERING = "DELIVERING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DELIVERED = "DELIVERED"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class NotificationConfiguration:  # pylint: disable=too-many-instance-attributes
    enabled: bool
    endpoint_url: str
    auth_type: NotificationAuthType
    auth_header_name: str | None
    secret_reference: str | None
    ticket_created_template: str
    ticket_replied_template: str
    success_status_codes: tuple[int, ...]
    timeout_seconds: int
    max_attempts: int
    retry_base_seconds: int
    id: UUID = field(default_factory=uuid4)
    updated_by: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("notification timeout must be between 1 and 120 seconds")
        if self.max_attempts <= 0 or self.max_attempts > 10:
            raise ValueError("notification max attempts must be between 1 and 10")
        if self.retry_base_seconds <= 0 or self.retry_base_seconds > 86_400:
            raise ValueError("notification retry base must be between 1 and 86400 seconds")
        if not self.success_status_codes or any(
            code < 200 or code > 299 for code in self.success_status_codes
        ):
            raise ValueError("notification success status codes must be 2xx")

    def template_for(self, event_type: NotificationEventType) -> str:
        if event_type is NotificationEventType.TICKET_CREATED:
            return self.ticket_created_template
        return self.ticket_replied_template


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    event_type: NotificationEventType
    recipient: str
    variables: dict[str, object]


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    status_code: int
    provider_message_id: str | None
    response_summary: str | None


@dataclass(frozen=True, slots=True)
class NotificationRecipient:
    account_id: UUID | None
    address: str


@dataclass(frozen=True, slots=True)
class OutboxEvent:  # pylint: disable=too-many-instance-attributes
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: NotificationEventType
    payload: dict[str, object]
    status: OutboxStatus
    idempotency_key: str
    created_at: datetime
    processed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NotificationDelivery:  # pylint: disable=too-many-instance-attributes
    id: UUID
    outbox_id: UUID
    event_type: NotificationEventType
    recipient_id: UUID | None
    recipient_address: str
    status: NotificationDeliveryStatus
    idempotency_key: str
    attempt_count: int
    cycle_attempt: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error_code: str | None
    last_error_message: str | None
    provider_message_id: str | None
    response_summary: str | None
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None
