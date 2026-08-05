from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from knowagent.agent.api.router import _consume_sse_token, _sse_token_key
from knowagent.agent.api.schemas import SseAuthToken


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, ex: int) -> bool:
        assert ex > 0
        self.values[key] = value
        return True

    def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


def _grant(*, account_id: UUID, token: str = "a" * 32) -> SseAuthToken:
    return SseAuthToken(
        token=token,
        account_id=account_id,
        run_id=uuid4(),
        system_id=uuid4(),
        question="如何发布？",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


def test_sse_token_is_bound_to_account_and_consumed_once() -> None:
    redis = FakeRedis()
    owner_id = uuid4()
    other_id = uuid4()
    grant = _grant(account_id=owner_id)
    redis.set(
        _sse_token_key(owner_id, grant.token),
        grant.model_dump_json(),
        ex=120,
    )

    assert _consume_sse_token(redis, token=grant.token, account_id=other_id) is None
    consumed = _consume_sse_token(redis, token=grant.token, account_id=owner_id)
    assert consumed is not None
    assert consumed.account_id == owner_id
    assert _consume_sse_token(redis, token=grant.token, account_id=owner_id) is None


def test_sse_token_rejects_payload_bound_to_another_account() -> None:
    redis = FakeRedis()
    account_id = uuid4()
    mismatched = _grant(account_id=uuid4())
    redis.set(
        _sse_token_key(account_id, mismatched.token),
        mismatched.model_dump_json(),
        ex=120,
    )

    assert _consume_sse_token(redis, token=mismatched.token, account_id=account_id) is None
