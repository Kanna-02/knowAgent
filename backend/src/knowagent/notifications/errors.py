from __future__ import annotations


class NotificationError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class TransientNotificationError(NotificationError):
    """A provider failure that can be retried automatically."""


class PermanentNotificationError(NotificationError):
    """A configuration or provider failure requiring operator action."""
