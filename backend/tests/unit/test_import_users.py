from pathlib import Path

import pytest

from knowagent.identity.import_users import ImportRowError, load_import_rows
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher


def test_load_import_rows_accepts_only_argon2id_hashes(tmp_path: Path) -> None:
    source = tmp_path / "users.csv"
    password_hash = Argon2PasswordHasher().hash("Replacement2@")
    source.write_text(
        "username,display_name,password_hash,role,credential_batch\n"
        f'alice,Alice,"{password_hash}",USER,batch-1\n',
        encoding="utf-8",
    )

    rows = load_import_rows(source)

    assert rows[0].username == "alice"
    assert rows[0].must_change_password is True


@pytest.mark.parametrize(
    "password_hash",
    ["Temporary1!", "$argon2i$v=19$bad", "$argon2id$v=19$bad", ""],
)
def test_load_import_rows_rejects_plaintext_or_non_argon2id_hash(
    tmp_path: Path, password_hash: str
) -> None:
    source = tmp_path / "users.csv"
    source.write_text(
        "username,display_name,password_hash,role,credential_batch\n"
        f"alice,Alice,{password_hash},USER,batch-1\n",
        encoding="utf-8",
    )

    with pytest.raises(ImportRowError):
        load_import_rows(source)
