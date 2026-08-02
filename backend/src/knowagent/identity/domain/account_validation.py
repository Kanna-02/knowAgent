from __future__ import annotations

import re


_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def normalize_username(value: str) -> str:
    normalized = value.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("账号格式不正确")
    return normalized


def normalize_display_name(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 100:
        raise ValueError("显示名称不能为空且不能超过 100 个字符")
    return normalized
