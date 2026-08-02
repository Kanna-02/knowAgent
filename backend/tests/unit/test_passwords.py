from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher


def test_hash_produces_argon2id_digest_and_verifies_password() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("Replacement2@")

    assert password_hash.startswith("$argon2id$")
    assert hasher.verify("Replacement2@", password_hash) is True


def test_verify_rejects_wrong_password() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("Replacement2@")

    assert hasher.verify("WrongPassword3#", password_hash) is False


def test_verify_rejects_invalid_hash_without_raising() -> None:
    assert Argon2PasswordHasher().verify("Replacement2@", "not-a-hash") is False
