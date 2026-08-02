from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from knowagent.identity.cli import (
    bootstrap_admin_command,
    hash_password_command,
    import_users_command,
)
from knowagent.identity.domain.models import AccountRole
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base


def test_hash_password_command_reads_secret_from_prompt_and_prints_only_digest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    password_inputs = ["Replacement2@", "Replacement2@"]
    passwords = iter(password_inputs)
    monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))

    hash_password_command()

    output = capsys.readouterr().out.strip()
    assert output.startswith("$argon2id$")
    assert "Replacement2@" not in output


def test_import_users_command_persists_prehashed_users_in_one_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "identity.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    source = tmp_path / "users.csv"
    with source.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["username", "display_name", "password_hash", "role", "credential_batch"])
        writer.writerow(
            [
                "alice",
                "Alice",
                Argon2PasswordHasher().hash("Replacement2@"),
                "USER",
                "batch-1",
            ]
        )
    monkeypatch.setenv("KNOWAGENT_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setattr(sys, "argv", ["knowagent-import-users", str(source)])

    import_users_command()

    with Session(engine) as session:
        account = session.scalar(select(AccountRecord).where(AccountRecord.username == "alice"))
    assert account is not None
    assert account.role is AccountRole.USER
    assert account.must_change_password is True
    assert "已导入 1 个用户" in capsys.readouterr().out


def test_bootstrap_admin_command_allows_only_the_first_admin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "identity.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("KNOWAGENT_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["knowagent-bootstrap-admin", "--username", "root.admin", "--display-name", "Root Admin"],
    )
    password_inputs = ["Replacement2@", "Replacement2@"]
    passwords = iter(password_inputs)
    monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))

    bootstrap_admin_command()

    with Session(engine) as session:
        count = session.scalar(
            select(func.count())
            .select_from(AccountRecord)
            .where(AccountRecord.role == AccountRole.ADMIN)
        )
    assert count == 1
    second_password_inputs = ["Replacement2@", "Replacement2@"]
    passwords = iter(second_password_inputs)
    monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))
    with pytest.raises(SystemExit, match="已有管理员"):
        bootstrap_admin_command()


def test_bootstrap_admin_command_rejects_unusable_username_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "identity.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("KNOWAGENT_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["knowagent-bootstrap-admin", "--username", "x", "--display-name", "Root Admin"],
    )

    with pytest.raises(SystemExit, match="账号格式不正确"):
        bootstrap_admin_command()

    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(AccountRecord))
    assert count == 0
