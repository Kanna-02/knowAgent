from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowagent.identity.domain.models import Account, AccountRole, AccountSource, AccountStatus


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    temporary_password: str = Field(min_length=12, max_length=256)

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("显示名称不能为空")
        return value


class AccountStatusRequest(BaseModel):
    status: AccountStatus


class CurrentUserView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    username: str
    display_name: str
    role: AccountRole
    status: AccountStatus
    must_change_password: bool
    system_roles: list[str] = Field(default_factory=list)

    @classmethod
    def from_account(cls, account: Account) -> CurrentUserView:
        return cls(
            id=account.id,
            username=account.username,
            display_name=account.display_name,
            role=account.role,
            status=account.status,
            must_change_password=account.must_change_password,
        )


class SessionView(BaseModel):
    user: CurrentUserView
    must_change_password: bool
    csrf_token: str
    expires_at: datetime


class AccountView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    username: str
    display_name: str
    role: AccountRole
    source: AccountSource
    status: AccountStatus
    must_change_password: bool
    credential_batch: str | None
    external_provider: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_account(cls, account: Account) -> AccountView:
        return cls(
            id=account.id,
            username=account.username,
            display_name=account.display_name,
            role=account.role,
            source=account.source,
            status=account.status,
            must_change_password=account.must_change_password,
            credential_batch=account.credential_batch,
            external_provider=account.external_provider,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )


class AccountPage(BaseModel):
    items: list[AccountView]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
