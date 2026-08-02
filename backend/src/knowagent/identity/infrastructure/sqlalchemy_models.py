from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus


def enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class Base(DeclarativeBase):
    pass


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("external_provider", "external_subject", name="uq_accounts_external_id"),
        Index("ix_accounts_role_status", "role", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AccountRole] = mapped_column(
        Enum(
            AccountRole,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="account_role",
        ),
        nullable=False,
    )
    source: Mapped[AccountSource] = mapped_column(
        Enum(
            AccountSource,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="account_source",
        ),
        nullable=False,
    )
    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="account_status",
        ),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    must_change_password: Mapped[bool] = mapped_column(nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_batch: Mapped[str | None] = mapped_column(String(64))
    external_provider: Mapped[str | None] = mapped_column(String(64))
    external_subject: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    context_data: Mapped[dict[str, str | int | bool] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    detail: Mapped[str | None] = mapped_column(Text)
