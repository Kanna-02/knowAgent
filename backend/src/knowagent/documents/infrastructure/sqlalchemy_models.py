from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from knowagent.documents.domain.ingestion import (
    DocumentVersionStatus,
    IngestionStage,
    IngestionStatus,
)
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.systems.infrastructure import sqlalchemy_models as systems_models

del systems_models

# SQLAlchemy's dynamic func namespace and declarative records trigger false positives.
# pylint: disable=not-callable,too-few-public-methods


def enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_system_updated", "system_id", "updated_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}


class DocumentVersionRecord(Base):  # pylint: disable=too-many-instance-attributes
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_versions_number"),
        UniqueConstraint("object_key", name="uq_document_versions_object_key"),
        Index("ix_document_versions_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentVersionStatus] = mapped_column(
        Enum(
            DocumentVersionStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="document_version_status",
        ),
        nullable=False,
    )
    chunk_manifest_key: Mapped[str | None] = mapped_column(String(1024))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_name: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}


class IngestionJobRecord(Base):  # pylint: disable=too-many-instance-attributes
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint("document_version_id", name="uq_ingestion_jobs_document_version"),
        UniqueConstraint(
            "actor_id",
            "system_id",
            "idempotency_key",
            name="uq_ingestion_jobs_idempotency_scope",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_ingestion_jobs_progress"),
        CheckConstraint("attempt >= 0", name="ck_ingestion_jobs_attempt"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts"),
        Index("ix_ingestion_jobs_dispatch", "status", "next_retry_at", "last_dispatched_at"),
        Index("ix_ingestion_jobs_lease", "status", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(
            IngestionStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ingestion_status",
        ),
        nullable=False,
    )
    stage: Mapped[IngestionStage] = mapped_column(
        Enum(
            IngestionStage,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="ingestion_stage",
        ),
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}
