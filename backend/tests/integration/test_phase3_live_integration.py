from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from _fakes import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from knowagent.agent.api.router import (
    _persist_stream_terminal_turn,
    _persist_stream_user_turn,
)
from knowagent.agent.domain.conversation import IntentKind, QueryRewriteResult
from knowagent.agent.domain.models import (
    EvidenceDecision,
    EvidenceDecisionOutcome,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.agent.infrastructure.sqlalchemy_models import (
    ConversationRecord,
    EvidenceDecisionRecord,
    PromptDefinitionRecord,
    RetrievalProfileRecord,
)
from knowagent.api.app import create_app
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, AuditLogRecord
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.settings import Settings
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("KNOWAGENT_RUN_API_INTEGRATION") != "1",
        reason="set KNOWAGENT_RUN_API_INTEGRATION=1 to run live API integration tests",
    ),
]

PASSWORD = "Temporary1!"
ACCOUNT_USERNAMES = ("phase3.live.user.one", "phase3.live.user.two", "phase3.live.admin")
SYSTEM_CODE = "PHASE3LIVE"
PROMPT_VERSION = "query-rewrite-live-v2"
PROFILE_VERSION = "profile-live-v2"


@pytest.fixture()
def live_client() -> Iterator[TestClient]:
    database_url = os.getenv("KNOWAGENT_API_INTEGRATION_DATABASE_URL", "")
    if not database_url:
        pytest.skip("KNOWAGENT_API_INTEGRATION_DATABASE_URL not set")
    engine = create_database_engine(database_url)
    factory = create_session_factory(engine)
    _cleanup(factory)
    _seed(factory)
    app = create_app(_settings(database_url))
    app.state.redis_client = FakeRedis()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client
    finally:
        app.state.engine.dispose()
        _cleanup(factory)
        engine.dispose()


def test_phase3_versions_conversations_and_terminal_persistence_on_postgresql(
    live_client: TestClient,
) -> None:
    factory = live_client.app.state.session_factory
    with factory() as session:
        seeded_prompts = session.scalars(
            select(PromptDefinitionRecord).where(PromptDefinitionRecord.enabled.is_(True))
        ).all()
        seeded_profiles = session.scalars(
            select(RetrievalProfileRecord).where(RetrievalProfileRecord.is_active.is_(True))
        ).all()
        index_rows = session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE indexname IN "
                "('uq_prompt_definitions_active_scenario', "
                "'uq_retrieval_profiles_active_name')"
            )
        ).all()
    assert {(item.scenario, item.version) for item in seeded_prompts} == {
        ("grounded_answer", "grounded-answer-v1"),
        ("query_rewrite", "query-rewrite-v1"),
    }
    assert [(item.name, item.version) for item in seeded_profiles] == [("default", "profile-v1")]
    assert len(index_rows) == 2
    assert all(" WHERE " in str(row.indexdef).upper() for row in index_rows)

    admin_session = _login(live_client, "admin", ACCOUNT_USERNAMES[2])
    admin_headers = {"X-CSRF-Token": str(admin_session["csrf_token"])}
    prompt_response = live_client.post(
        "/api/v1/admin/prompt-definitions",
        headers=admin_headers,
        json={
            "scenario": "query_rewrite",
            "version": PROMPT_VERSION,
            "content": "将追问改写为独立检索问题，只输出改写结果。",
            "change_note": "PostgreSQL live integration",
        },
    )
    assert prompt_response.status_code == 201, prompt_response.text
    activated_prompt = live_client.post(
        "/api/v1/admin/prompt-definitions/activate",
        headers=admin_headers,
        json={"scenario": "query_rewrite", "version": PROMPT_VERSION},
    )
    assert activated_prompt.status_code == 200, activated_prompt.text
    assert activated_prompt.json()["enabled"] is True

    profile_response = live_client.post(
        "/api/v1/admin/retrieval-profiles",
        headers=admin_headers,
        json={
            "name": "default",
            "version": PROFILE_VERSION,
            "keyword_top_k": 24,
            "vector_top_k": 24,
            "result_top_k": 10,
            "rrf_k": 60,
            "keyword_weight": 1.2,
            "vector_weight": 1.0,
            "rerank_candidate_top_k": 20,
            "rerank_top_k": 10,
            "evidence_max_items": 6,
            "evidence_max_characters": 12000,
            "change_note": "PostgreSQL live integration",
        },
    )
    assert profile_response.status_code == 201, profile_response.text
    activated_profile = live_client.post(
        "/api/v1/admin/retrieval-profiles/activate",
        headers=admin_headers,
        json={"name": "default", "version": PROFILE_VERSION},
    )
    assert activated_profile.status_code == 200, activated_profile.text
    assert activated_profile.json()["is_active"] is True

    first_session = _login(live_client, "user", ACCOUNT_USERNAMES[0])
    system_id = _system_id(factory)
    created = live_client.post(
        "/api/v1/conversations",
        headers={"X-CSRF-Token": str(first_session["csrf_token"])},
        json={"system_id": str(system_id), "title": "Phase 3 live conversation"},
    )
    assert created.status_code == 201, created.text
    conversation_id = UUID(created.json()["id"])

    with factory.begin() as database:
        account_id = database.scalar(
            select(AccountRecord.id).where(AccountRecord.username == ACCOUNT_USERNAMES[0])
        )
        assert account_id is not None
        rewrite = QueryRewriteResult(
            intent=IntentKind.FOLLOW_UP,
            rewritten_query="ESB 发布流程",
            original_query="那怎么发布？",
            prompt_version=PROMPT_VERSION,
        )
        now = datetime.now(UTC)
        _persist_stream_user_turn(
            database=database,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            question="那怎么发布？",
            rewrite=rewrite,
            now=now,
        )
        _persist_stream_terminal_turn(
            database=database,
            system_id=system_id,
            account_id=account_id,
            conversation_id=conversation_id,
            event=QuestionStreamEvent(
                kind=QuestionStreamEventKind.ANSWER_COMPLETED,
                payload=VerifiedAnswer(
                    text="先审核，再发布。",
                    claims=(),
                    citations=(),
                    model="live-test",
                    prompt_version="grounded-answer-v1",
                ),
                run_id=uuid4(),
            ),
            now=now,
        )
        run_id = uuid4()
        SqlAlchemyTicketRepository(database).add_decision(
            decision=EvidenceDecision(
                id=uuid4(),
                run_id=run_id,
                system_id=system_id,
                query="ESB 发布流程",
                normalized_query="esb 发布流程",
                outcome=EvidenceDecisionOutcome.SUFFICIENT,
                reason_codes=(),
                score=0.03,
                applied_score_threshold=0.015,
                policy_version="evidence-v1",
                candidates=(),
                degraded_reasons=(),
                decided_at=datetime.now(UTC),
                retrieval_profile_name="default",
                retrieval_profile_version=PROFILE_VERSION,
            ),
            ticket_id=None,
        )

    with factory() as database:
        stored_decision = database.scalar(
            select(EvidenceDecisionRecord).where(EvidenceDecisionRecord.run_id == run_id)
        )
        assert stored_decision is not None
        assert stored_decision.retrieval_profile_name == "default"
        assert stored_decision.retrieval_profile_version == PROFILE_VERSION

    detail = live_client.get(f"/api/v1/conversations/{conversation_id}")
    assert detail.status_code == 200, detail.text
    assert [message["content"] for message in detail.json()["messages"]] == [
        "那怎么发布？",
        "先审核，再发布。",
    ]
    assert detail.json()["messages"][0]["intent"] == "follow_up"
    assert detail.json()["messages"][0]["rewritten_query"] == "ESB 发布流程"
    assert detail.json()["messages"][0]["rewrite_prompt_version"] == PROMPT_VERSION

    _login(live_client, "user", ACCOUNT_USERNAMES[1])
    assert live_client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404


def _settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        redis_url="redis://unused",
        redis_prefix="test-phase3-live",
        session_cookie_name="knowagent_session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="integration",
    )


def _seed(factory: sessionmaker[Session]) -> None:
    password_hash = Argon2PasswordHasher().hash(PASSWORD)
    with factory.begin() as session:
        session.add_all(
            [
                _account(ACCOUNT_USERNAMES[0], AccountRole.USER, password_hash),
                _account(ACCOUNT_USERNAMES[1], AccountRole.USER, password_hash),
                _account(ACCOUNT_USERNAMES[2], AccountRole.ADMIN, password_hash),
                BusinessSystemRecord(
                    id=uuid4(),
                    code=SYSTEM_CODE,
                    name="Phase 3 Live Integration",
                    description="Phase 3 PostgreSQL integration test",
                    status=BusinessSystemStatus.ACTIVE,
                ),
            ]
        )


def _account(username: str, role: AccountRole, password_hash: str) -> AccountRecord:
    return AccountRecord(
        id=uuid4(),
        username=username,
        display_name=username,
        password_hash=password_hash,
        role=role,
        source=AccountSource.ADMIN_CREATED,
        status=AccountStatus.ACTIVE,
        must_change_password=False,
        session_version=1,
    )


def _login(client: TestClient, entry: str, username: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/auth/{entry}/sessions",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _system_id(factory: sessionmaker[Session]) -> UUID:
    with factory() as session:
        system_id = session.scalar(
            select(BusinessSystemRecord.id).where(BusinessSystemRecord.code == SYSTEM_CODE)
        )
    assert system_id is not None
    return system_id


def _cleanup(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        system_ids = tuple(
            session.scalars(
                select(BusinessSystemRecord.id).where(BusinessSystemRecord.code == SYSTEM_CODE)
            )
        )
        account_ids = tuple(
            session.scalars(
                select(AccountRecord.id).where(AccountRecord.username.in_(ACCOUNT_USERNAMES))
            )
        )
        if account_ids:
            session.execute(delete(AuditLogRecord).where(AuditLogRecord.actor_id.in_(account_ids)))
            session.execute(
                delete(ConversationRecord).where(ConversationRecord.account_id.in_(account_ids))
            )
        if system_ids:
            session.execute(
                delete(EvidenceDecisionRecord).where(
                    EvidenceDecisionRecord.system_id.in_(system_ids)
                )
            )
        session.execute(
            delete(PromptDefinitionRecord).where(PromptDefinitionRecord.version == PROMPT_VERSION)
        )
        session.execute(
            delete(RetrievalProfileRecord).where(RetrievalProfileRecord.version == PROFILE_VERSION)
        )
        session.execute(
            update(PromptDefinitionRecord)
            .where(PromptDefinitionRecord.version == "query-rewrite-v1")
            .values(enabled=True)
        )
        session.execute(
            update(RetrievalProfileRecord)
            .where(RetrievalProfileRecord.version == "profile-v1")
            .values(is_active=True)
        )
        session.execute(
            delete(BusinessSystemRecord).where(BusinessSystemRecord.code == SYSTEM_CODE)
        )
        session.execute(delete(AccountRecord).where(AccountRecord.username.in_(ACCOUNT_USERNAMES)))
