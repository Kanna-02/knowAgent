from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.api.router import (
    _consume_sse_token,
    _persist_stream_terminal_turn,
    _persist_stream_user_turn,
    _render_event,
    _sse_token_key,
    _stream_resolution,
)
from knowagent.agent.api.schemas import SseAuthToken
from knowagent.agent.application.conversation_service import ConversationService
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.conversation import (
    ConversationMessageRole,
    IntentKind,
    QueryRewriteResult,
)
from knowagent.agent.domain.models import (
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.common.errors import NotFoundError
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord


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


def test_refused_sse_payload_preserves_explicit_degradation_reasons() -> None:
    run_id = uuid4()
    system_id = uuid4()
    decision = EvidenceDecision(
        id=uuid4(),
        run_id=run_id,
        system_id=system_id,
        query="如何发布？",
        normalized_query="如何发布",
        outcome=EvidenceDecisionOutcome.INSUFFICIENT,
        reason_codes=(EvidenceReasonCode.NO_EVIDENCE,),
        score=None,
        applied_score_threshold=0.015,
        policy_version="evidence-v1",
        candidates=(),
        degraded_reasons=("VECTOR_UNAVAILABLE", "RERANK_UNAVAILABLE"),
        decided_at=datetime.now(UTC),
        ticket_id=uuid4(),
    )
    rendered = _render_event(
        QuestionStreamEvent(
            kind=QuestionStreamEventKind.REFUSED,
            payload=decision,
            run_id=run_id,
            degraded_reasons=decision.degraded_reasons,
        ),
        system_id=system_id,
        question="如何发布？",
    )

    assert rendered is not None
    payload = json.loads(rendered.decode().removeprefix("data: "))
    assert payload["type"] == "refused"
    assert payload["degraded_reasons"] == ["VECTOR_UNAVAILABLE", "RERANK_UNAVAILABLE"]


@pytest.mark.anyio
async def test_stream_unexpected_failure_emits_terminal_error_event() -> None:
    class FailingQuestionService:
        retrieval_profile_name = "default"
        retrieval_profile_version = "profile-v1"

        async def resolve_stream(self, **_kwargs: object) -> AsyncIterator[QuestionStreamEvent]:
            raise RuntimeError("retrieval crashed")
            yield  # Make this an async generator for the service protocol.

    chunks = [
        chunk
        async for chunk in _stream_resolution(
            cast(ReliableQuestionService, FailingQuestionService()),
            run_id=uuid4(),
            requester_id=uuid4(),
            system_id=uuid4(),
            question="库外问题",
            required_terms=(),
        )
    ]

    assert len(chunks) == 1
    payload = json.loads(chunks[0].decode().removeprefix("data: "))
    assert payload["type"] == "error"
    assert payload["code"] == "QUESTION_STREAM_FAILED"


def test_stream_user_prelude_persists_user_question() -> None:
    with _conversation_session() as (session, account_id, system_id, conversation_id):
        rewrite = QueryRewriteResult(
            intent=IntentKind.FOLLOW_UP,
            rewritten_query="ESB 发布流程",
            original_query="那怎么发布？",
            prompt_version="query-rewrite-v1",
        )
        now = datetime.now(UTC)
        _persist_stream_user_turn(
            database=session,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            question="那怎么发布？",
            rewrite=rewrite,
            now=now,
        )
        messages = ConversationService(session).list_messages(
            conversation_id=conversation_id,
            system_id=system_id,
        )
        assert [message.content for message in messages] == ["那怎么发布？"]
        assert messages[0].role is ConversationMessageRole.USER
        assert messages[0].intent is IntentKind.FOLLOW_UP
        assert messages[0].rewrite_prompt_version == "query-rewrite-v1"


def test_stream_terminal_answer_persists_assistant_turn() -> None:
    with _conversation_session() as (session, account_id, system_id, conversation_id):
        answer = VerifiedAnswer(
            text="先审核，再发布。",
            claims=(),
            citations=(),
            model="test",
            prompt_version="grounded-answer-v1",
        )
        _persist_stream_terminal_turn(
            database=session,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            event=QuestionStreamEvent(
                kind=QuestionStreamEventKind.ANSWER_COMPLETED,
                payload=answer,
                run_id=uuid4(),
            ),
            now=datetime.now(UTC),
        )
        messages = ConversationService(session).list_messages(
            conversation_id=conversation_id,
            system_id=system_id,
        )
        assert [message.content for message in messages] == ["先审核，再发布。"]
        assert messages[0].role is ConversationMessageRole.ASSISTANT


def test_stream_user_prelude_and_terminal_answer_persist_full_turn() -> None:
    with _conversation_session() as (session, account_id, system_id, conversation_id):
        rewrite = QueryRewriteResult(
            intent=IntentKind.FOLLOW_UP,
            rewritten_query="ESB 发布流程",
            original_query="那怎么发布？",
            prompt_version="query-rewrite-v1",
        )
        now = datetime.now(UTC)
        _persist_stream_user_turn(
            database=session,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            question="那怎么发布？",
            rewrite=rewrite,
            now=now,
        )
        answer = VerifiedAnswer(
            text="先审核，再发布。",
            claims=(),
            citations=(),
            model="test",
            prompt_version="grounded-answer-v1",
        )
        _persist_stream_terminal_turn(
            database=session,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            event=QuestionStreamEvent(
                kind=QuestionStreamEventKind.ANSWER_COMPLETED,
                payload=answer,
                run_id=uuid4(),
            ),
            now=now,
        )
        messages = ConversationService(session).list_messages(
            conversation_id=conversation_id,
            system_id=system_id,
        )
        assert [message.content for message in messages] == ["那怎么发布？", "先审核，再发布。"]
        assert messages[0].intent is IntentKind.FOLLOW_UP
        assert messages[0].rewrite_prompt_version == "query-rewrite-v1"


def test_stream_non_terminal_event_does_not_persist_turn() -> None:
    with _conversation_session() as (session, account_id, system_id, conversation_id):
        _persist_stream_terminal_turn(
            database=session,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            event=QuestionStreamEvent(
                kind=QuestionStreamEventKind.RETRIEVAL_STARTED,
                payload=None,
                run_id=uuid4(),
            ),
            now=datetime.now(UTC),
        )
        assert (
            ConversationService(session).list_messages(
                conversation_id=conversation_id,
                system_id=system_id,
            )
            == ()
        )


def test_stream_terminal_rejects_foreign_conversation() -> None:
    with _conversation_session() as (session, _account_id, system_id, conversation_id):
        with pytest.raises(NotFoundError):
            _persist_stream_terminal_turn(
                database=session,
                system_id=system_id,
                account_id=uuid4(),
                conversation_id=conversation_id,
                event=QuestionStreamEvent(
                    kind=QuestionStreamEventKind.REFUSED,
                    payload=None,
                    run_id=uuid4(),
                ),
                now=datetime.now(UTC),
            )


class _ConversationSession:
    _session: Session

    def __enter__(self) -> tuple[Session, UUID, UUID, UUID]:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self._session = Session(engine)
        account_id = uuid4()
        system_id = uuid4()
        now = datetime.now(UTC)
        self._session.add(
            AccountRecord(
                id=account_id,
                username="stream-user",
                display_name="Stream User",
                password_hash="dummy",
                role=AccountRole.USER,
                source=AccountSource.ADMIN_CREATED,
                status=AccountStatus.ACTIVE,
                must_change_password=False,
                session_version=1,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.add(
            BusinessSystemRecord(
                id=system_id,
                code="STREAM",
                name="Stream",
                description=None,
                status=BusinessSystemStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.flush()
        conversation = ConversationService(self._session).create_conversation(
            system_id=system_id,
            account_id=account_id,
            title="Stream",
            now=now,
        )
        return self._session, account_id, system_id, conversation.id

    def __exit__(self, *_args: object) -> None:
        self._session.close()


def _conversation_session() -> _ConversationSession:
    return _ConversationSession()
