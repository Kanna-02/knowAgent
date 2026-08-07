from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
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
        UniqueConstraint("run_id", "system_id", name="uq_evidence_decisions_run_system"),
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
        CheckConstraint(
            "(retrieval_profile_name IS NULL) = (retrieval_profile_version IS NULL)",
            name="ck_evidence_decisions_retrieval_profile_pair",
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
    retrieval_profile_name: Mapped[str | None] = mapped_column(String(64))
    retrieval_profile_version: Mapped[str | None] = mapped_column(String(100))
    candidate_summaries: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE,
        nullable=False,
        default=list,
    )
    degraded_reasons: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnswerRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("id", "system_id", name="uq_answers_id_system"),
        Index("ix_answers_system_created", "system_id", "created_at"),
        ForeignKeyConstraint(
            ["run_id", "system_id"],
            ["evidence_decisions.run_id", "evidence_decisions.system_id"],
            ondelete="RESTRICT",
            name="fk_answers_run_system",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[list[dict[str, object]]] = mapped_column(JSON_VALUE, nullable=False)
    degraded_reasons: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnswerCitationRecord(Base):  # pylint: disable=too-few-public-methods
    __tablename__ = "answer_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["answer_id", "system_id"],
            ["answers.id", "answers.system_id"],
            ondelete="CASCADE",
            name="fk_answer_citations_answer_system",
        ),
        Index("ix_answer_citations_source", "system_id", "source_id"),
        Index("ix_answer_citations_answer_rank", "answer_id", "rank", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    answer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    locators: Mapped[list[dict[str, object]]] = mapped_column(JSON_VALUE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationRecord(Base):  # pylint: disable=too-few-public-methods
    """A multi-turn conversation scoped to an account and business system."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "system_id", name="uq_conversations_id_system"),
        Index("ix_conversations_account_updated", "account_id", "updated_at"),
        Index("ix_conversations_system_updated", "system_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationMessageRecord(Base):  # pylint: disable=too-few-public-methods
    """A single message persisted on a conversation turn."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "system_id"],
            ["conversations.id", "conversations.system_id"],
            ondelete="CASCADE",
            name="fk_conversation_messages_conversation_system",
        ),
        Index(
            "ix_conversation_messages_conversation_sequence",
            "conversation_id",
            "sequence_number",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(16))
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    rewrite_prompt_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptDefinitionRecord(Base):  # pylint: disable=too-few-public-methods
    """Versioned prompt definitions stored in the database.

    The packaged ``grounded_answer_v1.json`` resource remains the fallback when
    the database has no enabled row for a scenario; DB rows allow multiple
    versions to coexist with a single active version per scenario.
    """

    __tablename__ = "prompt_definitions"
    __table_args__ = (
        UniqueConstraint("scenario", "version", name="uq_prompt_definitions_scenario_version"),
        Index("ix_prompt_definitions_scenario_enabled", "scenario", "enabled"),
        Index(
            "uq_prompt_definitions_active_scenario",
            "scenario",
            unique=True,
            postgresql_where=text("enabled"),
            sqlite_where=text("enabled = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_note: Mapped[str] = mapped_column(String(500), nullable=False)


class RetrievalProfileRecord(Base):  # pylint: disable=too-few-public-methods
    """Named, versioned retrieval parameter profiles stored in the database."""

    __tablename__ = "retrieval_profiles"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_retrieval_profiles_name_version"),
        Index("ix_retrieval_profiles_name_active", "name", "is_active"),
        Index(
            "uq_retrieval_profiles_active_name",
            "name",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    keyword_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    result_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    rrf_k: Mapped[int] = mapped_column(Integer, nullable=False)
    keyword_weight: Mapped[float] = mapped_column(Float, nullable=False)
    vector_weight: Mapped[float] = mapped_column(Float, nullable=False)
    rerank_candidate_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_max_items: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_max_characters: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_note: Mapped[str] = mapped_column(String(500), nullable=False)
