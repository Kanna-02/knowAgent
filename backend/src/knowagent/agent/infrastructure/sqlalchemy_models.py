from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from knowagent.agent.domain.models import EvidenceDecisionOutcome
from knowagent.identity.infrastructure.sqlalchemy_models import Base, enum_values
from knowagent.systems.infrastructure import sqlalchemy_models as system_models

del system_models

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class EvidenceDecisionRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "evidence_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="RESTRICT",
            name="fk_evidence_decisions_ticket_system",
        ),
        Index(
            "ix_evidence_decisions_system_outcome_created",
            "system_id",
            "outcome",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ticket_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[EvidenceDecisionOutcome] = mapped_column(
        Enum(
            EvidenceDecisionOutcome,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="evidence_decision_outcome",
        ),
        nullable=False,
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    score: Mapped[float | None] = mapped_column(Float)
    applied_score_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_summaries: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE,
        nullable=False,
        default=list,
    )
    degraded_reasons: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
