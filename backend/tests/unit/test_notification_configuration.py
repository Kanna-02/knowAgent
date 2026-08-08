from __future__ import annotations

import pytest

from knowagent.common.errors import ValidationError
from knowagent.notifications.application.configuration import validate_notification_endpoint
from knowagent.notifications.domain.models import NotificationAuthType, NotificationConfiguration
from knowagent.platform.settings import NotificationRuntimeSettings, Settings


def configuration(
    endpoint_url: str,
    *,
    enabled: bool = True,
) -> NotificationConfiguration:
    template = '{"receiver":"${recipient}"}'
    return NotificationConfiguration(
        enabled=enabled,
        endpoint_url=endpoint_url,
        auth_type=NotificationAuthType.NONE,
        auth_header_name=None,
        secret_reference=None,
        ticket_created_template=template,
        ticket_replied_template=template,
        success_status_codes=(200, 202),
        timeout_seconds=5,
        max_attempts=3,
        retry_base_seconds=10,
    )


def settings(
    *,
    environment: str = "production",
    allowed_hosts: tuple[str, ...] = ("notify.example.test",),
) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://127.0.0.1:6379/0",
        redis_prefix="test",
        session_cookie_name="test_session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=8,
        login_window_seconds=900,
        environment=environment,
        notifications=NotificationRuntimeSettings(allowed_hosts=allowed_hosts),
    )


def test_disabled_notification_allows_a_blank_endpoint() -> None:
    validate_notification_endpoint(configuration("", enabled=False), settings=settings())


@pytest.mark.parametrize(
    "endpoint_url",
    [
        "ftp://notify.example.test/messages",
        "https:///messages",
        "https://user:password@notify.example.test/messages",
    ],
)
def test_notification_endpoint_rejects_invalid_urls(endpoint_url: str) -> None:
    with pytest.raises(ValidationError, match="通知地址格式无效"):
        validate_notification_endpoint(configuration(endpoint_url), settings=settings())


def test_notification_endpoint_rejects_fragments() -> None:
    with pytest.raises(ValidationError, match="通知地址不能包含片段"):
        validate_notification_endpoint(
            configuration("https://notify.example.test/messages#callback"),
            settings=settings(),
        )


def test_production_notification_endpoint_requires_https() -> None:
    with pytest.raises(ValidationError, match="生产环境通知地址必须使用 HTTPS"):
        validate_notification_endpoint(
            configuration("http://notify.example.test/messages"),
            settings=settings(),
        )


@pytest.mark.parametrize("allowed_hosts", [(), ("other.example.test",)])
def test_production_notification_endpoint_enforces_allowlist(
    allowed_hosts: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError, match="通知地址不在生产环境允许域名中"):
        validate_notification_endpoint(
            configuration("https://notify.example.test/messages"),
            settings=settings(allowed_hosts=allowed_hosts),
        )


def test_allowed_production_and_development_endpoints_pass() -> None:
    validate_notification_endpoint(
        configuration("https://notify.example.test/messages"),
        settings=settings(),
    )
    validate_notification_endpoint(
        configuration("http://localhost:8080/messages"),
        settings=settings(environment="development", allowed_hosts=()),
    )
