from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationConfiguration,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
)
from knowagent.notifications.template import (
    NotificationTemplateError,
    validate_notification_template,
)


class NotificationConfigurationUpdate(BaseModel):  # pylint: disable=no-member
    enabled: bool
    endpoint_url: str = Field(max_length=2048)
    auth_type: NotificationAuthType
    auth_header_name: str | None = Field(default=None, max_length=128)
    secret_reference: str | None = Field(default=None, max_length=128)
    ticket_created_template: str = Field(min_length=2, max_length=32768)
    ticket_replied_template: str = Field(min_length=2, max_length=32768)
    success_status_codes: tuple[int, ...] = Field(min_length=1, max_length=10)
    timeout_seconds: int = Field(ge=1, le=120)
    max_attempts: int = Field(ge=1, le=10)
    retry_base_seconds: int = Field(ge=1, le=86400)

    @field_validator("ticket_created_template", "ticket_replied_template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        try:
            validate_notification_template(value)
        except NotificationTemplateError as error:
            raise ValueError(str(error)) from error
        return value

    @field_validator("success_status_codes")
    @classmethod
    def validate_success_codes(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value) or any(code < 200 or code > 299 for code in value):
            raise ValueError("success status codes must be unique 2xx values")
        return tuple(sorted(value))

    # Pylint resolves Pydantic model fields as FieldInfo inside model validators.
    # pylint: disable=no-member
    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        if self.auth_type is NotificationAuthType.NONE:
            return self
        if not self.auth_header_name or not self.auth_header_name.strip():
            raise ValueError("auth header name is required")
        if not self.secret_reference or not self.secret_reference.strip():
            raise ValueError("secret reference is required")
        if not self.auth_header_name.replace("-", "").isalnum():
            raise ValueError("auth header name is invalid")
        reference = self.secret_reference
        if not reference.replace("_", "").isalnum() or not reference[0].isalpha():
            raise ValueError("secret reference must be an environment variable name")
        return self

    # pylint: enable=no-member


class NotificationConfigurationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enabled: bool
    endpoint_url: str
    auth_type: NotificationAuthType
    auth_header_name: str | None
    secret_reference: str | None
    ticket_created_template: str
    ticket_replied_template: str
    success_status_codes: tuple[int, ...]
    timeout_seconds: int
    max_attempts: int
    retry_base_seconds: int
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_configuration(
        cls, configuration: NotificationConfiguration
    ) -> NotificationConfigurationView:
        return cls.model_validate(configuration)


class NotificationDeliveryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outbox_id: UUID
    event_type: NotificationEventType
    recipient_id: UUID | None
    recipient_address: str
    status: NotificationDeliveryStatus
    idempotency_key: str
    attempt_count: int
    cycle_attempt: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error_code: str | None
    last_error_message: str | None
    provider_message_id: str | None
    response_summary: str | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_delivery(cls, delivery: NotificationDelivery) -> NotificationDeliveryView:
        return cls.model_validate(delivery)


class NotificationDeliveryPage(BaseModel):
    items: list[NotificationDeliveryView]
    page: int
    page_size: int
    total: int
