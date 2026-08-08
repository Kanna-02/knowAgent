from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, Session, mapped_column

from knowagent.identity.infrastructure.sqlalchemy_models import Base


class OutboxEventRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
        Index("ix_outbox_events_status_created", "status", "created_at"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SqlAlchemyOutboxWriter:  # pylint: disable=too-few-public-methods,too-many-arguments
    def __init__(self, session: Session) -> None:
        self._session = session

    def publish(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, object],
        idempotency_key: str,
        occurred_at: datetime,
    ) -> OutboxEventRecord:  # pylint: disable=too-many-arguments
        if occurred_at.tzinfo is None:
            raise ValueError("outbox event time must be timezone-aware")
        event = OutboxEventRecord(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
            idempotency_key=idempotency_key,
            created_at=occurred_at,
        )
        self._session.add(event)
        self._session.flush()
        return event
