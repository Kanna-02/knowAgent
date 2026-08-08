from __future__ import annotations

from typing import Protocol

from knowagent.notifications.domain.models import (
    DeliveryReceipt,
    NotificationConfiguration,
    NotificationRequest,
)


class NotificationProvider(Protocol):  # pylint: disable=too-few-public-methods
    async def send(
        self,
        *,
        configuration: NotificationConfiguration,
        request: NotificationRequest,
        idempotency_key: str,
    ) -> DeliveryReceipt: ...
