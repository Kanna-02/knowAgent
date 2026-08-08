from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationDeliveryStatus,
    NotificationEventType,
)

# SQLAlchemy exposes SQL functions dynamically; Pylint cannot infer that call contract.
# pylint: disable=not-callable


def enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class NotificationConfigurationRecord(
    Base
):  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    __tablename__ = "notification_configurations"
    __table_args__ = (UniqueConstraint("name", name="uq_notification_configurations_name"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    auth_type: Mapped[NotificationAuthType] = mapped_column(
        Enum(
            NotificationAuthType,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=16,
            name="notification_auth_type",
        ),
        nullable=False,
    )
    auth_header_name: Mapped[str | None] = mapped_column(String(128))
    secret_reference: Mapped[str | None] = mapped_column(String(128))
    ticket_created_template: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_replied_template: Mapped[str] = mapped_column(Text, nullable=False)
    success_status_codes: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_base_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class NotificationDeliveryRecord(
    Base
):  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_deliveries_idempotency_key"),
        Index("ix_notification_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_notification_deliveries_event_created", "event_type", "created_at"),
        Index("ix_notification_deliveries_outbox", "outbox_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    outbox_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[NotificationEventType] = mapped_column(
        Enum(
            NotificationEventType,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="notification_event_type",
        ),
        nullable=False,
    )
    recipient_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    recipient_address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        Enum(
            NotificationDeliveryStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="notification_delivery_status",
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(320), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cycle_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_attempt_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    response_summary: Mapped[str | None] = mapped_column(String(500))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
