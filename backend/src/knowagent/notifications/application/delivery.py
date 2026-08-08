from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from knowagent.notifications.domain.models import (
    NotificationConfiguration,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)
from knowagent.notifications.errors import NotificationError, TransientNotificationError
from knowagent.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)
from knowagent.notifications.ports import NotificationProvider

LOGGER = logging.getLogger(__name__)


class NotificationPreparationService:  # pylint: disable=too-few-public-methods
    def __init__(self, *, repository: SqlAlchemyNotificationRepository) -> None:
        self._repository = repository

    def prepare_pending(self, *, now: datetime, limit: int) -> int:
        if now.tzinfo is None:
            raise ValueError("notification preparation time must be timezone-aware")
        configuration = self._repository.get_configuration()
        processed = 0
        for event in self._repository.list_pending_events(limit=limit):
            recipients = self._repository.resolve_recipients(event)
            if not recipients:
                recipients = (NotificationRecipient(None, "unresolved"),)
                status = NotificationDeliveryStatus.PERMANENT_FAILURE
                error_code = "RECIPIENT_NOT_FOUND"
                error_message = "通知接收人不存在或已禁用"
            elif configuration is None or not configuration.enabled:
                status = NotificationDeliveryStatus.SKIPPED
                error_code = "NOTIFICATION_DISABLED"
                error_message = "通知配置未启用"
            else:
                status = NotificationDeliveryStatus.PENDING
                error_code = None
                error_message = None
            for recipient in recipients:
                self._repository.add_delivery(
                    event=event,
                    recipient=recipient,
                    status=status,
                    now=now,
                    error_code=error_code,
                    error_message=error_message,
                )
            self._repository.mark_event_processed(event.id, now=now)
            processed += 1
        return processed


class NotificationDeliveryProcessor:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        provider: NotificationProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))

    async def deliver(self, *, delivery_id: UUID, now: datetime) -> NotificationDelivery:
        if now.tzinfo is None:
            raise ValueError("notification delivery time must be timezone-aware")
        with self._session_factory.begin() as session:
            claimed = SqlAlchemyNotificationRepository(session).claim_delivery(delivery_id, now=now)
        if claimed is None:
            with self._session_factory() as session:
                delivery = SqlAlchemyNotificationRepository(session).get_delivery(delivery_id)
                if delivery is None:
                    raise ValueError("notification delivery disappeared after claim")
                return delivery
        delivery, configuration, request, attempt_id = claimed
        try:
            receipt = await self._provider.send(
                configuration=configuration,
                request=request,
                idempotency_key=delivery.idempotency_key,
            )
        except NotificationError as error:
            return self._record_failure(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                error=error,
                configuration=configuration,
                now=self._clock(),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            LOGGER.exception(
                "unexpected notification provider failure", extra={"delivery_id": str(delivery_id)}
            )
            wrapped = TransientNotificationError(
                "PROVIDER_INTERNAL_ERROR", "notification provider failed unexpectedly"
            )
            return self._record_failure(
                delivery_id=delivery_id,
                attempt_id=attempt_id,
                error=wrapped,
                configuration=configuration,
                now=self._clock(),
            )
        with self._session_factory.begin() as session:
            return SqlAlchemyNotificationRepository(session).record_success(
                delivery_id,
                attempt_id=attempt_id,
                status_code=receipt.status_code,
                provider_message_id=receipt.provider_message_id,
                response_summary=receipt.response_summary,
                now=self._clock(),
            )

    def _record_failure(
        self,
        *,
        delivery_id: UUID,
        attempt_id: UUID,
        error: NotificationError,
        configuration: NotificationConfiguration,
        now: datetime,
    ) -> NotificationDelivery:
        with self._session_factory.begin() as session:
            return SqlAlchemyNotificationRepository(session).record_failure(
                delivery_id,
                attempt_id=attempt_id,
                error_code=error.code,
                error_message=error.message,
                status_code=error.status_code,
                retryable=isinstance(error, TransientNotificationError),
                maximum_attempts=configuration.max_attempts,
                retry_base_seconds=configuration.retry_base_seconds,
                now=now,
            )
