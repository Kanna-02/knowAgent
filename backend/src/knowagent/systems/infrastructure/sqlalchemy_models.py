from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import (
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
from knowagent.systems.domain.models import BusinessSystemStatus, SystemRole


def enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class BusinessSystemRecord(Base):
    __tablename__ = "business_systems"
    __table_args__ = (Index("ix_business_systems_status_code", "status", "code"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BusinessSystemStatus] = mapped_column(
        Enum(
            BusinessSystemStatus,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="business_system_status",
        ),
        nullable=False,
        default=BusinessSystemStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class AccountSystemRoleRecord(Base):
    __tablename__ = "account_system_roles"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "system_id", "role", name="uq_account_system_roles_assignment"
        ),
        Index("ix_account_system_roles_system_role", "system_id", "role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    system_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("business_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[SystemRole] = mapped_column(
        Enum(
            SystemRole,
            values_callable=enum_values,
            native_enum=False,
            create_constraint=True,
            length=32,
            name="system_role",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
