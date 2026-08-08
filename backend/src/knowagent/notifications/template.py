from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import cast

ALLOWED_TEMPLATE_VARIABLES = frozenset(
    {
        "active",
        "attempt",
        "created_at",
        "event_id",
        "event_type",
        "question",
        "recipient",
        "recipient_id",
        "reply_body",
        "system_id",
        "system_name",
        "ticket_id",
        "title",
    }
)
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.]*)\}")
_EXACT_QUOTED_PLACEHOLDER = re.compile(r'"\$\{([A-Za-z_][A-Za-z0-9_.]*)\}"')


class NotificationTemplateError(ValueError):
    pass


def validate_notification_template(template: str) -> None:
    if len(template.encode("utf-8")) > 32_768:
        raise NotificationTemplateError("notification template exceeds 32768 bytes")
    names = set(_PLACEHOLDER.findall(template))
    unknown = sorted(names - ALLOWED_TEMPLATE_VARIABLES)
    if unknown:
        raise NotificationTemplateError(f"unknown placeholder: {unknown[0]}")
    dummy = {name: "value" for name in names}
    rendered = render_notification_template(template, dummy)
    if not rendered:
        raise NotificationTemplateError("notification template must be a non-empty JSON object")


def render_notification_template(
    template: str,
    variables: Mapping[str, object],
) -> dict[str, object]:
    names = set(_PLACEHOLDER.findall(template))
    unknown = sorted(names - ALLOWED_TEMPLATE_VARIABLES)
    if unknown:
        raise NotificationTemplateError(f"unknown placeholder: {unknown[0]}")
    missing = sorted(name for name in names if name not in variables)
    if missing:
        raise NotificationTemplateError(f"missing placeholder value: {missing[0]}")

    def replace_exact(match: re.Match[str]) -> str:
        return json.dumps(variables[match.group(1)], ensure_ascii=False, separators=(",", ":"))

    rendered = _EXACT_QUOTED_PLACEHOLDER.sub(replace_exact, template)

    rendered = _replace_remaining_placeholders(rendered, variables)
    try:
        parsed: object = json.loads(rendered)
    except json.JSONDecodeError as error:
        raise NotificationTemplateError(
            f"notification template is invalid JSON: {error.msg}"
        ) from error
    if not isinstance(parsed, dict) or not parsed:
        raise NotificationTemplateError("notification template must be a non-empty JSON object")
    if not all(isinstance(key, str) for key in parsed):
        raise NotificationTemplateError("notification template keys must be strings")
    return cast(dict[str, object], parsed)


def _replace_remaining_placeholders(
    template: str,
    variables: Mapping[str, object],
) -> str:
    parts: list[str] = []
    position = 0
    for match in _PLACEHOLDER.finditer(template):
        parts.append(template[position : match.start()])
        value = variables[match.group(1)]
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        parts.append(encoded[1:-1] if _inside_json_string(template, match.start()) else encoded)
        position = match.end()
    parts.append(template[position:])
    return "".join(parts)


def _inside_json_string(value: str, position: int) -> bool:
    inside = False
    escaped = False
    for character in value[:position]:
        if escaped:
            escaped = False
        elif character == "\\" and inside:
            escaped = True
        elif character == '"':
            inside = not inside
    return inside
