from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowagent.systems.domain.models import (
    BusinessSystem,
    BusinessSystemStatus,
    SystemOwner,
    SystemRole,
    SystemRoleAssignment,
)


class SystemOwnerView(BaseModel):
    account_id: UUID
    username: str
    display_name: str

    @classmethod
    def from_owner(cls, owner: SystemOwner) -> SystemOwnerView:
        return cls(
            account_id=owner.account_id,
            username=owner.username,
            display_name=owner.display_name,
        )


class SystemRoleView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    system_id: UUID
    role: SystemRole

    @classmethod
    def from_assignment(cls, assignment: SystemRoleAssignment) -> SystemRoleView:
        return cls(system_id=assignment.system_id, role=assignment.role)


class BusinessSystemView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    code: str
    name: str
    description: str | None
    status: BusinessSystemStatus
    owners: list[SystemOwnerView]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_system(cls, business_system: BusinessSystem) -> BusinessSystemView:
        return cls(
            id=business_system.id,
            code=business_system.code,
            name=business_system.name,
            description=business_system.description,
            status=business_system.status,
            owners=[SystemOwnerView.from_owner(owner) for owner in business_system.owners],
            created_at=business_system.created_at,
            updated_at=business_system.updated_at,
        )


class BusinessSystemPage(BaseModel):
    items: list[BusinessSystemView]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class SystemCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: BusinessSystemStatus = BusinessSystemStatus.ACTIVE


class SystemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: BusinessSystemStatus | None = None


class OwnerAssignmentRequest(BaseModel):
    account_ids: list[UUID] = Field(max_length=100)
    replace_existing: bool = True

    @field_validator("account_ids")
    @classmethod
    def account_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("负责人账号不能重复")
        return value
