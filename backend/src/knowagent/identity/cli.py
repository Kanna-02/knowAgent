from __future__ import annotations

import argparse
import getpass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.identity.application.auth_service import password_violations
from knowagent.identity.domain.account_validation import normalize_display_name, normalize_username
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.import_users import load_import_rows
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.settings import Settings


_ADMIN_BOOTSTRAP_LOCK_ID = 1_265_660_574_325_345


def hash_password_command() -> None:
    password = getpass.getpass("临时密码：")
    confirmation = getpass.getpass("再次输入：")
    if password != confirmation:
        raise SystemExit("两次密码输入不一致")
    violations = password_violations(password)
    if violations:
        raise SystemExit("密码不符合策略：" + "；".join(violations))
    print(Argon2PasswordHasher().hash(password))


def import_users_command() -> None:
    parser = argparse.ArgumentParser(description="从受控 CSV 批量导入本地用户")
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    rows = load_import_rows(args.csv_file)
    settings = Settings.from_environment()
    factory = create_session_factory(create_database_engine(settings.database_url))
    now = datetime.now(UTC)
    with factory.begin() as session:
        existing = set(
            session.scalars(
                select(AccountRecord.username).where(
                    AccountRecord.username.in_([row.username for row in rows])
                )
            ).all()
        )
        if existing:
            raise SystemExit("以下账号已存在：" + ", ".join(sorted(existing)))
        session.add_all(
            [
                AccountRecord(
                    id=uuid4(),
                    username=row.username,
                    display_name=row.display_name,
                    password_hash=row.password_hash,
                    role=row.role,
                    source=AccountSource.LOCAL_IMPORT,
                    status=AccountStatus.ACTIVE,
                    must_change_password=True,
                    session_version=1,
                    credential_batch=row.credential_batch,
                    created_at=now,
                    updated_at=now,
                )
                for row in rows
            ]
        )
    print(f"已导入 {len(rows)} 个用户；所有账号首次登录均需改密。")


def bootstrap_admin_command() -> None:
    parser = argparse.ArgumentParser(description="初始化首个平台管理员")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    try:
        username = normalize_username(args.username)
        display_name = normalize_display_name(args.display_name)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    password = getpass.getpass("管理员临时密码：")
    confirmation = getpass.getpass("再次输入：")
    if password != confirmation:
        raise SystemExit("两次密码输入不一致")
    violations = password_violations(password)
    if violations:
        raise SystemExit("密码不符合策略：" + "；".join(violations))
    settings = Settings.from_environment()
    factory = create_session_factory(create_database_engine(settings.database_url))
    with factory.begin() as session:
        _lock_admin_bootstrap(session)
        _assert_no_admin(session)
        now = datetime.now(UTC)
        session.add(
            AccountRecord(
                id=uuid4(),
                username=username,
                display_name=display_name,
                password_hash=Argon2PasswordHasher().hash(password),
                role=AccountRole.ADMIN,
                source=AccountSource.ADMIN_CREATED,
                status=AccountStatus.ACTIVE,
                must_change_password=True,
                session_version=1,
                created_at=now,
                updated_at=now,
            )
        )
    print(f"管理员 {username} 已初始化；首次登录必须改密。")


def _assert_no_admin(session: Session) -> None:
    existing_admin = session.scalar(
        select(AccountRecord.id).where(AccountRecord.role == AccountRole.ADMIN).limit(1)
    )
    if existing_admin is not None:
        raise SystemExit("已有管理员，后续管理员必须从后台新增")


def _lock_admin_bootstrap(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_ADMIN_BOOTSTRAP_LOCK_ID)))
