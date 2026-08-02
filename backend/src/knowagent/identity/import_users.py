from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError

from knowagent.identity.domain.account_validation import normalize_display_name, normalize_username
from knowagent.identity.domain.models import AccountRole


class ImportRowError(ValueError):
    def __init__(self, row_number: int, message: str) -> None:
        super().__init__(f"第 {row_number} 行：{message}")
        self.row_number = row_number


@dataclass(frozen=True, slots=True)
class ImportUserRow:
    username: str
    display_name: str
    password_hash: str
    role: AccountRole
    credential_batch: str
    must_change_password: bool = True


def load_import_rows(path: Path) -> list[ImportUserRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {
            "username",
            "display_name",
            "password_hash",
            "role",
            "credential_batch",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ImportRowError(1, "缺少必填列")
        rows = [_parse_row(row, row_number) for row_number, row in enumerate(reader, start=2)]
    if not rows:
        raise ImportRowError(2, "导入文件没有用户数据")
    usernames = [row.username for row in rows]
    if len(usernames) != len(set(usernames)):
        raise ImportRowError(2, "导入文件包含重复账号")
    return rows


def _parse_row(row: dict[str, str | None], row_number: int) -> ImportUserRow:
    try:
        username = normalize_username(row.get("username") or "")
        display_name = normalize_display_name(row.get("display_name") or "")
    except ValueError as error:
        raise ImportRowError(row_number, str(error)) from error
    password_hash = (row.get("password_hash") or "").strip()
    role_value = (row.get("role") or "").strip().upper()
    credential_batch = (row.get("credential_batch") or "").strip()

    if not password_hash.startswith("$argon2id$"):
        raise ImportRowError(row_number, "password_hash 必须是 Argon2id 摘要，禁止明文密码")
    try:
        extract_parameters(password_hash)
    except InvalidHashError as error:
        raise ImportRowError(row_number, "password_hash 不是有效的 Argon2id 摘要") from error
    try:
        role = AccountRole(role_value)
    except ValueError as error:
        raise ImportRowError(row_number, "角色必须是 USER 或 SYSTEM_OWNER") from error
    if role is AccountRole.ADMIN:
        raise ImportRowError(row_number, "批量导入不能创建管理员")
    if not credential_batch or len(credential_batch) > 64:
        raise ImportRowError(row_number, "凭据批次不能为空且不能超过 64 个字符")
    return ImportUserRow(
        username=username,
        display_name=display_name,
        password_hash=password_hash,
        role=role,
        credential_batch=credential_batch,
    )
