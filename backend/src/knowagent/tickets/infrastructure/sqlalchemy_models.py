from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from knowagent.identity.infrastructure.sqlalchemy_models import Base, enum_values
from knowagent.tickets.domain.models import (
    CandidateStatus,
    ReplyAuthorRole,
    TicketPriority,
    TicketStatus,
)


class TicketRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("id", "system_id", name="uq_tickets_id_system"),
        CheckConstraint("occurrence_count > 0", name="ck_tickets_occurrence_count"),
        Index("ix_tickets_system_status_assignee", "system_id", "status", "assignee_id"),
        Index(
            "ix_tickets_system_deduplication_updated",
            "system_id",
            "deduplication_key",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requester_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ticket_status",
        ),
        nullable=False,
        default=TicketStatus.OPEN,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ticket_priority",
        ),
        nullable=False,
        default=TicketPriority.NORMAL,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(64), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}


class TicketOccurrenceRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "ticket_occurrences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_occurrences_ticket_system",
        ),
        Index(
            "ix_ticket_occurrences_requester_created",
            "requester_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_decisions.run_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    requester_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TicketReplyRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "ticket_replies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_replies_ticket_system",
        ),
        Index("ix_ticket_replies_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_role: Mapped[ReplyAuthorRole] = mapped_column(
        Enum(
            ReplyAuthorRole,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="reply_author_role",
        ),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TicketTransitionRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "ticket_transitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_ticket_transitions_ticket_system",
        ),
        Index("ix_ticket_transitions_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[TicketStatus | None] = mapped_column(
        Enum(
            TicketStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ticket_transition_from_status",
        ),
        nullable=True,
    )
    to_status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ticket_transition_to_status",
        ),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeCandidateRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "knowledge_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "system_id"],
            ["tickets.id", "tickets.system_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_ticket_system",
        ),
        ForeignKeyConstraint(
            ["knowledge_source_id"],
            ["knowledge_sources.id"],
            ondelete="RESTRICT",
            name="fk_knowledge_candidates_source",
        ),
        Index("ix_knowledge_candidates_ticket_status", "ticket_id", "status"),
        Index("ix_knowledge_candidates_system_updated", "system_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
    )
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(
            CandidateStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="candidate_status",
        ),
        nullable=False,
        default=CandidateStatus.PENDING,
    )
    knowledge_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}
