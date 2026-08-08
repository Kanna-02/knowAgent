from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy.orm import Session

from knowagent.identity.api.dependencies import AdminContext, AdminCsrfContext, DatabaseSession
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink
from knowagent.notifications.api.schemas import (
    NotificationConfigurationUpdate,
    NotificationConfigurationView,
    NotificationDeliveryPage,
    NotificationDeliveryView,
)
from knowagent.notifications.application.configuration import validate_notification_endpoint
from knowagent.notifications.domain.models import (
    NotificationAuthType,
    NotificationConfiguration,
    NotificationDeliveryStatus,
    NotificationEventType,
)
from knowagent.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)

# FastAPI endpoint signatures expose validated request parameters explicitly.
# pylint: disable=too-many-arguments,too-many-positional-arguments

router = APIRouter()

_DEFAULT_CREATED_TEMPLATE = (
    '{"receiver":"${recipient}","title":"${title}","ticket_id":"${ticket_id}"}'
)
_DEFAULT_REPLIED_TEMPLATE = (
    '{"receiver":"${recipient}","title":"${title}","content":"${reply_body}"}'
)


@router.get(
    "/admin/notification-configuration",
    response_model=NotificationConfigurationView,
)
def get_notification_configuration(
    context: AdminContext,
    database: DatabaseSession,
) -> NotificationConfigurationView:
    del context
    configuration = SqlAlchemyNotificationRepository(database).get_configuration()
    return NotificationConfigurationView.from_configuration(
        configuration or _default_configuration()
    )


@router.put(
    "/admin/notification-configuration",
    response_model=NotificationConfigurationView,
)
def save_notification_configuration(
    payload: NotificationConfigurationUpdate,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> NotificationConfigurationView:
    now = datetime.now(UTC)
    current = SqlAlchemyNotificationRepository(database).get_configuration()
    configuration = NotificationConfiguration(
        id=current.id if current is not None else uuid4(),
        enabled=payload.enabled,
        endpoint_url=payload.endpoint_url.strip(),
        auth_type=payload.auth_type,
        auth_header_name=_optional_strip(payload.auth_header_name),
        secret_reference=_optional_strip(payload.secret_reference),
        ticket_created_template=payload.ticket_created_template,
        ticket_replied_template=payload.ticket_replied_template,
        success_status_codes=payload.success_status_codes,
        timeout_seconds=payload.timeout_seconds,
        max_attempts=payload.max_attempts,
        retry_base_seconds=payload.retry_base_seconds,
        updated_by=context.account.id,
        created_at=current.created_at if current is not None else now,
        updated_at=now,
    )
    validate_notification_endpoint(configuration, settings=request.app.state.settings)
    saved = SqlAlchemyNotificationRepository(database).save_configuration(configuration)
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="notification_configuration.update",
        object_id=saved.id,
        metadata={"enabled": saved.enabled, "auth_type": saved.auth_type.value},
    )
    return NotificationConfigurationView.from_configuration(saved)


@router.get(
    "/admin/notification-deliveries",
    response_model=NotificationDeliveryPage,
)
def list_notification_deliveries(
    context: AdminContext,
    database: DatabaseSession,
    delivery_status: Annotated[NotificationDeliveryStatus | None, Query(alias="status")] = None,
    event_type: Annotated[NotificationEventType | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationDeliveryPage:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    del context
    items, total = SqlAlchemyNotificationRepository(database).list_deliveries(
        status=delivery_status,
        event_type=event_type,
        page=page,
        page_size=page_size,
    )
    return NotificationDeliveryPage(
        items=[NotificationDeliveryView.from_delivery(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/admin/notification-deliveries/{delivery_id}/retry",
    response_model=NotificationDeliveryView,
)
def retry_notification_delivery(
    delivery_id: UUID,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> NotificationDeliveryView:
    delivery = SqlAlchemyNotificationRepository(database).retry_delivery(
        delivery_id=delivery_id,
        now=datetime.now(UTC),
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="notification_delivery.retry",
        object_id=delivery.id,
        metadata={"attempt_count": delivery.attempt_count},
    )
    return NotificationDeliveryView.from_delivery(delivery)


def _default_configuration() -> NotificationConfiguration:
    now = datetime.now(UTC)
    return NotificationConfiguration(
        enabled=False,
        endpoint_url="",
        auth_type=NotificationAuthType.NONE,
        auth_header_name=None,
        secret_reference=None,
        ticket_created_template=_DEFAULT_CREATED_TEMPLATE,
        ticket_replied_template=_DEFAULT_REPLIED_TEMPLATE,
        success_status_codes=(200, 201, 202, 204),
        timeout_seconds=5,
        max_attempts=3,
        retry_base_seconds=30,
        created_at=now,
        updated_at=now,
    )


def _optional_strip(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _record_audit(
    *,
    database: Session,
    request: Request,
    actor_id: UUID,
    action: str,
    object_id: UUID,
    metadata: dict[str, str | int | bool],
) -> None:  # pylint: disable=too-many-arguments
    SqlAlchemyAuditSink(database).record(
        action,
        "success",
        actor_id=actor_id,
        object_type="notification",
        object_id=object_id,
        request_id=request.state.request_id,
        metadata=metadata,
    )
