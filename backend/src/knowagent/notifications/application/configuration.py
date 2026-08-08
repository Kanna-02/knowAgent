from __future__ import annotations

from urllib.parse import urlsplit

from knowagent.common.errors import ValidationError
from knowagent.notifications.domain.models import NotificationConfiguration
from knowagent.platform.settings import Settings


def validate_notification_endpoint(
    configuration: NotificationConfiguration,
    *,
    settings: Settings,
) -> None:
    if not configuration.enabled and not configuration.endpoint_url.strip():
        return
    parsed = urlsplit(configuration.endpoint_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValidationError("NOTIFICATION_ENDPOINT_INVALID", "通知地址格式无效")
    if parsed.fragment:
        raise ValidationError("NOTIFICATION_ENDPOINT_INVALID", "通知地址不能包含片段")
    if settings.environment.lower() == "production":
        if parsed.scheme != "https":
            raise ValidationError("NOTIFICATION_HTTPS_REQUIRED", "生产环境通知地址必须使用 HTTPS")
        allowed_hosts = settings.notifications.allowed_hosts
        if not allowed_hosts or host not in allowed_hosts:
            raise ValidationError("NOTIFICATION_HOST_DENIED", "通知地址不在生产环境允许域名中")
