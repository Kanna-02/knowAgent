from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from _fakes import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from knowagent.agent.application.reliable_question import QuestionResolution
from knowagent.agent.domain.models import (
    CitationSnapshot,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    QuestionResolutionStatus,
    VerifiedAnswer,
    VerifiedClaim,
)
from knowagent.agent.infrastructure.sqlalchemy_models import (
    EvidenceDecisionRecord,
)
from knowagent.api.app import create_app
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.platform.settings import LlmSettings, Settings
from knowagent.systems.domain.models import BusinessSystemStatus
from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    TicketRecord,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("KNOWAGENT_RUN_API_INTEGRATION") != "1",
        reason="set KNOWAGENT_RUN_API_INTEGRATION=1 to run live API integration tests",
    ),
]

PASSWORD = "Temporary1!"
SYSTEM_NAMES = ("Agent API Integration System",)
ACCOUNT_NAMES = ("Agent API Integration Admin", "Agent API Integration User")


def _build_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        redis_url="redis://unused",
        redis_prefix="test-agent-api",
        session_cookie_name="knowagent_session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="integration",
        llm=LlmSettings(
            base_url="http://fake:1234",
            api_key="fake",
            model="fake-model",
        ),
    )


@pytest.fixture()
def client() -> Iterator[TestClient]:
    url = os.getenv("KNOWAGENT_API_INTEGRATION_DATABASE_URL", "")
    if not url:
        pytest.skip("KNOWAGENT_API_INTEGRATION_DATABASE_URL not set")
    from knowagent.platform.database import create_database_engine, create_session_factory

    engine = create_database_engine(url)
    factory = create_session_factory(engine)
    _cleanup(factory)
    _seed(factory)

    settings = _build_settings(url)
    app = create_app(settings)
    app.state.redis_client = FakeRedis()
    Base.metadata.create_all(app.state.engine)

    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client

    app.state.engine.dispose()
    _cleanup(factory)
    engine.dispose()


def _account(
    username: str,
    display_name: str,
    role: AccountRole,
    password_hash: str,
) -> AccountRecord:
    return AccountRecord(
        id=uuid4(),
        username=username,
        display_name=display_name,
        password_hash=password_hash,
        role=role,
        source=AccountSource.ADMIN_CREATED,
        status=AccountStatus.ACTIVE,
        must_change_password=False,
        session_version=1,
    )


def _seed(factory: sessionmaker[Session]) -> None:
    password_hash = Argon2PasswordHasher().hash(PASSWORD)
    system_id = uuid4()
    with factory.begin() as session:
        session.add(_account("agent.api.admin", ACCOUNT_NAMES[0], AccountRole.ADMIN, password_hash))
        session.add(_account("agent.api.user", ACCOUNT_NAMES[1], AccountRole.USER, password_hash))
        session.add(
            BusinessSystemRecord(
                id=system_id,
                code="AGENTAPI01",
                name=SYSTEM_NAMES[0],
                description="Agent API integration system",
                status=BusinessSystemStatus.ACTIVE,
            )
        )


def _cleanup(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        system_ids = tuple(
            session.scalars(
                select(BusinessSystemRecord.id).where(BusinessSystemRecord.name.in_(SYSTEM_NAMES))
            )
        )
        account_ids = tuple(
            session.scalars(
                select(AccountRecord.id).where(AccountRecord.display_name.in_(ACCOUNT_NAMES))
            )
        )
        if system_ids:
            session.execute(
                delete(EvidenceDecisionRecord).where(
                    EvidenceDecisionRecord.system_id.in_(system_ids)
                )
            )
            session.execute(delete(TicketRecord).where(TicketRecord.system_id.in_(system_ids)))
            session.execute(
                delete(BusinessSystemRecord).where(BusinessSystemRecord.id.in_(system_ids))
            )
        if account_ids:
            session.execute(delete(AccountRecord).where(AccountRecord.id.in_(account_ids)))


def _login(client: TestClient, entry: str, username: str) -> dict[str, object]:
    resp = client.post(
        f"/api/v1/auth/{entry}/sessions",
        json={"username": username, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_test_system_id(client: TestClient) -> str:
    from knowagent.platform.database import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    with factory() as session:
        system = session.scalar(
            select(BusinessSystemRecord).where(BusinessSystemRecord.name.in_(SYSTEM_NAMES))
        )
        assert system is not None
        return str(system.id)


def _get_account_id(client: TestClient, display_name: str) -> str:
    from knowagent.platform.database import create_session_factory

    factory = create_session_factory(client.app.state.engine)
    with factory() as session:
        account = session.scalar(
            select(AccountRecord).where(AccountRecord.display_name == display_name)
        )
        assert account is not None
        return str(account.id)


def _make_refused_resolution(system_id: UUID) -> QuestionResolution:
    decision = EvidenceDecision(
        id=uuid4(),
        run_id=uuid4(),
        system_id=system_id,
        query="query",
        normalized_query="query",
        outcome=EvidenceDecisionOutcome.INSUFFICIENT,
        reason_codes=(EvidenceReasonCode.NO_EVIDENCE,),
        score=None,
        applied_score_threshold=0.015,
        policy_version="evidence-v1",
        candidates=(),
        degraded_reasons=(),
        decided_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        ticket_id=uuid4(),
    )
    return QuestionResolution(
        status=QuestionResolutionStatus.REFUSED,
        decision=decision,
        answer=None,
        ticket_id=decision.ticket_id,
        reason_codes=decision.reason_codes,
        degraded_reasons=(),
    )


def _make_answered_resolution(system_id: UUID) -> QuestionResolution:
    decision = EvidenceDecision(
        id=uuid4(),
        run_id=uuid4(),
        system_id=system_id,
        query="query",
        normalized_query="query",
        outcome=EvidenceDecisionOutcome.SUFFICIENT,
        reason_codes=(),
        score=0.99,
        applied_score_threshold=0.015,
        policy_version="evidence-v1",
        candidates=(),
        degraded_reasons=(),
        decided_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        ticket_id=None,
    )
    locator = SourceLocator(
        source_type=SourceType.TICKET,
        block_index=0,
        ticket_id=uuid4(),
    )
    answer = VerifiedAnswer(
        text="ESB 接口超时设置为30秒。",
        claims=(VerifiedClaim(rank=1, text="超时30秒", citation_ranks=(1,)),),
        citations=(
            CitationSnapshot(
                rank=1,
                claim_rank=1,
                chunk_id=uuid4(),
                source_id=uuid4(),
                source_name="Source1",
                source_version="v1",
                quoted_text="ESB连接超时必须设置为30秒。",
                locators=(locator,),
            ),
        ),
        model="fake-model",
        prompt_version="grounded-answer-v1",
    )
    return QuestionResolution(
        status=QuestionResolutionStatus.ANSWERED,
        decision=decision,
        answer=answer,
        ticket_id=None,
        reason_codes=(),
        degraded_reasons=(),
    )


def _patch_question_service(resolution: QuestionResolution) -> object:
    from knowagent.agent.api import router as agent_router

    original = agent_router._build_question_service

    class _FakeService:
        async def resolve(self, **kwargs: object) -> QuestionResolution:
            return resolution

    def _patched(_request: object, _database: object) -> object:
        return _FakeService()

    agent_router._build_question_service = _patched  # type: ignore[assignment]
    return original


def _restore_question_service(original: object) -> None:
    from knowagent.agent.api import router as agent_router

    agent_router._build_question_service = original  # type: ignore[assignment]


def test_ask_question_unauthenticated_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/questions",
        json={"system_id": str(uuid4()), "question": "ESB 如何申请？"},
    )
    assert resp.status_code == 401


def test_ask_question_missing_csrf_returns_403(client: TestClient) -> None:
    _login(client, "admin", "agent.api.admin")
    resp = client.post(
        "/api/v1/questions",
        json={"system_id": str(uuid4()), "question": "ESB 如何申请？"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "CSRF_INVALID"


def test_ask_question_admin_system_not_found_returns_404(client: TestClient) -> None:
    login = _login(client, "admin", "agent.api.admin")
    csrf = str(login["csrf_token"])
    resp = client.post(
        "/api/v1/questions",
        headers={"X-CSRF-Token": csrf},
        json={"system_id": str(uuid4()), "question": "ESB 如何申请？"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "SYSTEM_NOT_FOUND"


def test_ask_question_validates_question_min_length(client: TestClient) -> None:
    system_id = _get_test_system_id(client)
    login = _login(client, "admin", "agent.api.admin")
    csrf = str(login["csrf_token"])
    resp = client.post(
        "/api/v1/questions",
        headers={"X-CSRF-Token": csrf},
        json={"system_id": system_id, "question": ""},
    )
    assert resp.status_code == 422


def test_ask_question_validates_system_id_required(client: TestClient) -> None:
    login = _login(client, "admin", "agent.api.admin")
    csrf = str(login["csrf_token"])
    resp = client.post(
        "/api/v1/questions",
        headers={"X-CSRF-Token": csrf},
        json={"question": "ESB 如何申请？"},
    )
    assert resp.status_code == 422


def test_ask_question_admin_returns_refused_when_insufficient(client: TestClient) -> None:
    system_id = _get_test_system_id(client)
    login = _login(client, "admin", "agent.api.admin")
    csrf = str(login["csrf_token"])
    resolution = _make_refused_resolution(system_id=UUID(system_id))
    original = _patch_question_service(resolution)
    try:
        resp = client.post(
            "/api/v1/questions",
            headers={"X-CSRF-Token": csrf},
            json={"system_id": system_id, "question": "ESB 如何申请？"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refused"
        assert data["answer"] is None
        assert data["ticket_id"] is not None
    finally:
        _restore_question_service(original)


def test_ask_question_admin_returns_answered(client: TestClient) -> None:
    system_id = _get_test_system_id(client)
    login = _login(client, "admin", "agent.api.admin")
    csrf = str(login["csrf_token"])
    resolution = _make_answered_resolution(system_id=UUID(system_id))
    original = _patch_question_service(resolution)
    try:
        resp = client.post(
            "/api/v1/questions",
            headers={"X-CSRF-Token": csrf},
            json={"system_id": system_id, "question": "ESB 如何申请？"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "answered"
        assert data["answer"]["text"] == "ESB 接口超时设置为30秒。"
        assert data["answer"]["model"] == "fake-model"
    finally:
        _restore_question_service(original)


def test_ask_question_user_can_query_active_system(client: TestClient) -> None:
    system_id = _get_test_system_id(client)
    login = _login(client, "user", "agent.api.user")
    csrf = str(login["csrf_token"])
    resolution = _make_answered_resolution(system_id=UUID(system_id))
    original = _patch_question_service(resolution)
    try:
        resp = client.post(
            "/api/v1/questions",
            headers={"X-CSRF-Token": csrf},
            json={"system_id": system_id, "question": "ESB 如何申请？"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "answered"
    finally:
        _restore_question_service(original)
