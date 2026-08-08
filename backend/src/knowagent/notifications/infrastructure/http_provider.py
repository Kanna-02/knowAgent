from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

import httpx

from knowagent.notifications.domain.models import (
    DeliveryReceipt,
    NotificationAuthType,
    NotificationConfiguration,
    NotificationRequest,
)
from knowagent.notifications.errors import (
    PermanentNotificationError,
    TransientNotificationError,
)
from knowagent.notifications.template import (
    NotificationTemplateError,
    render_notification_template,
)

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429})


class HttpNotificationProvider:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        allowed_hosts: tuple[str, ...],
        runtime_environment: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._environment = environment
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self._runtime_environment = runtime_environment.lower()
        self._transport = transport

    async def send(
        self,
        *,
        configuration: NotificationConfiguration,
        request: NotificationRequest,
        idempotency_key: str,
    ) -> DeliveryReceipt:
        self._validate_endpoint(configuration.endpoint_url)
        headers = self._headers(configuration, idempotency_key=idempotency_key)
        try:
            body = render_notification_template(
                configuration.template_for(request.event_type), request.variables
            )
        except NotificationTemplateError as error:
            raise PermanentNotificationError("TEMPLATE_INVALID", str(error)) from error
        content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(
                timeout=configuration.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    configuration.endpoint_url,
                    headers=headers,
                    content=content,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TransientNotificationError(
                "PROVIDER_UNAVAILABLE", "notification provider is temporarily unavailable"
            ) from error
        if response.status_code in configuration.success_status_codes:
            return DeliveryReceipt(
                status_code=response.status_code,
                provider_message_id=self._provider_message_id(response),
                response_summary=self._response_summary(response),
            )
        if response.status_code in _RETRYABLE_STATUS_CODES or response.status_code >= 500:
            raise TransientNotificationError(
                "PROVIDER_RETRYABLE_RESPONSE",
                "notification provider returned a retryable response",
                status_code=response.status_code,
            )
        raise PermanentNotificationError(
            "PROVIDER_REJECTED",
            "notification provider rejected the request",
            status_code=response.status_code,
        )

    def _validate_endpoint(self, endpoint_url: str) -> None:
        parsed = urlsplit(endpoint_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise PermanentNotificationError("ENDPOINT_INVALID", "notification endpoint is invalid")
        if self._runtime_environment == "production" and parsed.scheme != "https":
            raise PermanentNotificationError(
                "ENDPOINT_HTTPS_REQUIRED", "production notification endpoint must use HTTPS"
            )
        if self._runtime_environment == "production" and not self._allowed_hosts:
            raise PermanentNotificationError(
                "ENDPOINT_HOST_DENIED", "production notification host allowlist is empty"
            )
        if self._allowed_hosts and host not in self._allowed_hosts:
            raise PermanentNotificationError(
                "ENDPOINT_HOST_DENIED", "notification endpoint host is not allowed"
            )

    def _headers(
        self,
        configuration: NotificationConfiguration,
        *,
        idempotency_key: str,
    ) -> dict[str, str]:
        headers = {"Accept": "application/json", "Idempotency-Key": idempotency_key}
        if configuration.auth_type is NotificationAuthType.NONE:
            return headers
        reference = configuration.secret_reference or ""
        secret = self._environment.get(reference, "")
        if not secret:
            raise PermanentNotificationError(
                "SECRET_UNAVAILABLE", "notification credential reference is unavailable"
            )
        header_name = configuration.auth_header_name or "Authorization"
        headers[header_name] = (
            f"Bearer {secret}" if configuration.auth_type is NotificationAuthType.BEARER else secret
        )
        return headers

    @staticmethod
    def _provider_message_id(response: httpx.Response) -> str | None:
        if not response.content:
            return None
        try:
            parsed = cast(object, response.json())
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        value = parsed.get("message_id")
        return str(value) if isinstance(value, (str, int)) else None

    @staticmethod
    def _response_summary(response: httpx.Response) -> str | None:
        return f"HTTP {response.status_code}"
