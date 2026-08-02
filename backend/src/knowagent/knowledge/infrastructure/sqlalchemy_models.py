from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from knowagent.common.lifecycle import PublicationStatus
from knowagent.documents.infrastructure import sqlalchemy_models as document_models
from knowagent.documents.infrastructure.sqlalchemy_models import enum_values
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.domain.models import KnowledgeSourceType

del document_models

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")

# SQLAlchemy's dynamic func namespace and declarative records trigger false positives.
# pylint: disable=not-callable,too-few-public-methods


class KnowledgeSourceRecord(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("id", "system_id", name="uq_knowledge_sources_id_system"),
        UniqueConstraint("document_version_id", name="uq_knowledge_sources_document_version"),
        ForeignKeyConstraint(
            ["document_version_id", "system_id"],
            ["document_versions.id", "document_versions.system_id"],
            name="fk_knowledge_sources_version_system",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(source_type = 'DOCUMENT' AND document_version_id IS NOT NULL "
            "AND ticket_id IS NULL) OR "
            "(source_type = 'TICKET' AND ticket_id IS NOT NULL "
            "AND document_version_id IS NULL)",
            name="ck_knowledge_sources_reference",
        ),
        Index(
            "ix_knowledge_sources_system_publish",
            "system_id",
            "publish_status",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        Enum(
            KnowledgeSourceType,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="knowledge_source_type",
        ),
        nullable=False,
    )
    document_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    ticket_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    publish_status: Mapped[PublicationStatus] = mapped_column(
        Enum(
            PublicationStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="publication_status",
        ),
        nullable=False,
        default=PublicationStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "ordinal", name="uq_knowledge_chunks_source_ordinal"),
        ForeignKeyConstraint(
            ["source_id", "system_id"],
            ["knowledge_sources.id", "knowledge_sources.system_id"],
            name="fk_knowledge_chunks_source_system",
            ondelete="CASCADE",
        ),
        CheckConstraint("ordinal >= 0", name="ck_knowledge_chunks_ordinal"),
        CheckConstraint("token_count > 0", name="ck_knowledge_chunks_token_count"),
        Index(
            "ix_knowledge_chunks_system_publish",
            "system_id",
            "publish_status",
            "source_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    structure_path: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    locators: Mapped[list[dict[str, object]]] = mapped_column(JSON_VALUE, nullable=False)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_model_version: Mapped[str | None] = mapped_column(String(255))
    publish_status: Mapped[PublicationStatus] = mapped_column(
        Enum(
            PublicationStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="publication_status",
        ),
        nullable=False,
        default=PublicationStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
