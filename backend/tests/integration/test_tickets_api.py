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

from knowagent.agent.infrastructure.sqlalchemy_models import (
    EvidenceDecisionRecord,
)
from knowagent.api.app import create_app
from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
from knowagent.identity.infrastructure.passwords import Argon2PasswordHasher
from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord, Base
from knowagent.knowledge.infrastructure.sqlalchemy_models import (
    KnowledgeChunkRecord,
    KnowledgeSourceRecord,
)
from knowagent.platform.settings import Settings
from knowagent.retrieval.domain.models import EmbeddingBatch
from knowagent.systems.domain.models import BusinessSystemStatus, SystemRole
from knowagent.systems.infrastructure.sqlalchemy_models import (
    AccountSystemRoleRecord,
    BusinessSystemRecord,
)
from knowagent.tickets.domain.models import (
    ReplyAuthorRole,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    KnowledgeCandidateRecord,
    TicketOccurrenceRecord,
    TicketRecord,
    TicketReplyRecord,
    TicketTransitionRecord,
)
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("KNOWAGENT_RUN_API_INTEGRATION") != "1",
        reason="set KNOWAGENT_RUN_API_INTEGRATION=1 to run live API integration tests",
    ),
]

PASSWORD = "Temporary1!"
SYSTEM_NAMES = ("Tickets API Integration System",)
ACCOUNT_NAMES = (
    "Tickets API Integration Owner",
    "Tickets API Integration User",
    "Tickets API Integration Reviewer",
)


def _build_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        redis_url="redis://unused",
        redis_prefix="test-tickets-api",
        session_cookie_name="knowagent_session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="integration",
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
    account_id: UUID,
) -> AccountRecord:
    return AccountRecord(
        id=account_id,
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
    owner_id, user_id, reviewer_id = uuid4(), uuid4(), uuid4()
    system_id = uuid4()
    with factory.begin() as session:
        session.add(
            _account(
                "tickets.api.owner",
                ACCOUNT_NAMES[0],
                AccountRole.SYSTEM_OWNER,
                password_hash,
                owner_id,
            )
        )
        session.add(
            _account(
                "tickets.api.user",
                ACCOUNT_NAMES[1],
                AccountRole.USER,
                password_hash,
                user_id,
            )
        )
        session.add(
            _account(
                "tickets.api.reviewer",
                ACCOUNT_NAMES[2],
                AccountRole.ADMIN,
                password_hash,
                reviewer_id,
            )
        )
        session.add(
            BusinessSystemRecord(
                id=system_id,
                code="TICKETSAPI01",
                name=SYSTEM_NAMES[0],
                description="Tickets API integration system",
                status=BusinessSystemStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            AccountSystemRoleRecord(
                account_id=owner_id,
                system_id=system_id,
                role=SystemRole.SYSTEM_OWNER,
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
                delete(KnowledgeCandidateRecord).where(
                    KnowledgeCandidateRecord.system_id.in_(system_ids)
                )
            )
            session.execute(
                delete(KnowledgeChunkRecord).where(KnowledgeChunkRecord.system_id.in_(system_ids))
            )
            session.execute(
                delete(KnowledgeSourceRecord).where(KnowledgeSourceRecord.system_id.in_(system_ids))
            )
            session.execute(
                delete(TicketReplyRecord).where(TicketReplyRecord.system_id.in_(system_ids))
            )
            session.execute(
                delete(TicketTransitionRecord).where(
                    TicketTransitionRecord.system_id.in_(system_ids)
                )
            )
            session.execute(
                delete(TicketOccurrenceRecord).where(
                    TicketOccurrenceRecord.system_id.in_(system_ids)
                )
            )
            session.execute(
                delete(EvidenceDecisionRecord).where(
                    EvidenceDecisionRecord.system_id.in_(system_ids)
                )
            )
            session.execute(delete(TicketRecord).where(TicketRecord.system_id.in_(system_ids)))
            session.execute(
                delete(AccountSystemRoleRecord).where(
                    AccountSystemRoleRecord.system_id.in_(system_ids)
                )
            )
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


def _get_system_id(client: TestClient) -> str:
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


class _FakeEmbeddings:
    async def embed(self, *, texts: tuple[str, ...]) -> EmbeddingBatch:
        dimension = 1024
        unit = tuple(1.0 if i == 0 else 0.0 for i in range(dimension))
        vectors = tuple(unit for _ in texts)
        return EmbeddingBatch(
            model="fake-bge-m3",
            model_version="fake-v1",
            dimension=dimension,
            normalized=True,
            vectors=vectors,
        )


def _patch_review_service_embeddings() -> object:
    from knowagent.tickets.api import router as tickets_router
    from knowagent.tickets.application.review import KnowledgeReviewService

    original = tickets_router._build_review_service

    def _patched(request: object, database: object) -> object:
        return KnowledgeReviewService(
            repository=SqlAlchemyTicketRepository(database),
            embeddings=_FakeEmbeddings(),
        )

    tickets_router._build_review_service = _patched  # type: ignore[assignment]
    return original


def _restore_review_service_embeddings(original: object) -> None:
    from knowagent.tickets.api import router as tickets_router

    tickets_router._build_review_service = original  # type: ignore[assignment]


def _seed_ticket(client: TestClient, *, status: TicketStatus = TicketStatus.OPEN) -> str:
    from knowagent.platform.database import create_session_factory

    system = UUID(_get_system_id(client))
    requester = UUID(_get_account_id(client, ACCOUNT_NAMES[1]))
    factory = create_session_factory(client.app.state.engine)
    now = datetime.now(UTC)
    ticket = Ticket(
        id=uuid4(),
        system_id=system,
        requester_id=requester,
        source_run_id=uuid4(),
        assignee_id=None,
        status=status,
        priority=TicketPriority.NORMAL,
        title="ESB 参数无法识别怎么办？",
        question="ESB 参数无法识别怎么办？",
        normalized_question="esb 参数无法识别怎么办？".casefold(),
        deduplication_key=f"dedup-{uuid4()}",
        occurrence_count=1,
        created_at=now,
        updated_at=now,
    )
    with factory.begin() as session:
        repo = SqlAlchemyTicketRepository(session)
        repo.add_ticket(ticket)
    return str(ticket.id)


def test_list_tickets_owner_sees_tickets(client: TestClient) -> None:
    _login(client, "user", "tickets.api.owner")
    system_id = _get_system_id(client)
    ticket_id = _seed_ticket(client)
    resp = client.get("/api/v1/tickets", params={"system_id": system_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(item["id"] == ticket_id for item in data["items"])


def test_list_tickets_unauthenticated_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/tickets")
    assert resp.status_code == 401


def test_list_tickets_user_without_visible_systems_returns_empty(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression for cross-system leakage: when the user sees zero systems,
    # listing must short-circuit to an empty page rather than fall back to an
    # unfiltered full-table scan.
    from knowagent.tickets.api import router as tickets_router

    monkeypatch.setattr(
        tickets_router,
        "_visible_system_ids",
        lambda account, database: [],
    )
    _login(client, "user", "tickets.api.user")
    resp = client.get("/api/v1/tickets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_get_ticket_owner_can_view_and_replies_transitions(client: TestClient) -> None:
    _login(client, "user", "tickets.api.owner")
    ticket_id = _seed_ticket(client)
    get_resp = client.get(f"/api/v1/tickets/{ticket_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == ticket_id

    replies = client.get(f"/api/v1/tickets/{ticket_id}/replies")
    assert replies.status_code == 200
    assert isinstance(replies.json(), list)

    transitions = client.get(f"/api/v1/tickets/{ticket_id}/transitions")
    assert transitions.status_code == 200
    assert isinstance(transitions.json(), list)


def test_get_ticket_not_found(client: TestClient) -> None:
    _login(client, "user", "tickets.api.owner")
    resp = client.get(f"/api/v1/tickets/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "TICKET_NOT_FOUND"


def test_assign_ticket_and_start_and_resolve(client: TestClient) -> None:
    login = _login(client, "user", "tickets.api.owner")
    ticket_id = _seed_ticket(client)
    csrf = str(login["csrf_token"])

    assignee_id = _get_account_id(client, ACCOUNT_NAMES[2])
    assign_resp = client.post(
        f"/api/v1/tickets/{ticket_id}/assign",
        headers={"X-CSRF-Token": csrf},
        json={"assignee_id": assignee_id},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["status"] == "assigned"

    start_resp = client.post(
        f"/api/v1/tickets/{ticket_id}/start",
        headers={"X-CSRF-Token": csrf},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "in_progress"

    resolve_resp = client.post(
        f"/api/v1/tickets/{ticket_id}/resolve",
        headers={"X-CSRF-Token": csrf},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "resolved"


def test_reply_ticket_user_can_reply(client: TestClient) -> None:
    login = _login(client, "user", "tickets.api.user")
    ticket_id = _seed_ticket(client)
    csrf = str(login["csrf_token"])

    body = "补充：这个问题在新版本才出现的"
    resp = client.post(
        f"/api/v1/tickets/{ticket_id}/reply",
        headers={"X-CSRF-Token": csrf},
        json={"body": body},
    )
    assert resp.status_code == 201
    assert resp.json()["body"] == body


def test_close_and_reopen_ticket(client: TestClient) -> None:
    login = _login(client, "user", "tickets.api.owner")
    ticket_id = _seed_ticket(client, status=TicketStatus.RESOLVED)
    csrf = str(login["csrf_token"])

    close_resp = client.post(
        f"/api/v1/tickets/{ticket_id}/close",
        headers={"X-CSRF-Token": csrf},
        json={"body": "已确认关闭"},
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "closed"

    reopen_resp = client.post(
        f"/api/v1/tickets/{ticket_id}/reopen",
        headers={"X-CSRF-Token": csrf},
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "open"


def test_submit_answer_and_review_flow(client: TestClient) -> None:
    login = _login(client, "user", "tickets.api.owner")
    ticket_id = _seed_ticket(client, status=TicketStatus.IN_PROGRESS)
    csrf = str(login["csrf_token"])

    original = _patch_review_service_embeddings()
    try:
        answer_text = "ESB 连接超时应设为30秒。"
        submit_resp = client.post(
            f"/api/v1/tickets/{ticket_id}/answers",
            headers={"X-CSRF-Token": csrf},
            json={"answer": answer_text},
        )
        assert submit_resp.status_code == 201
        candidate = submit_resp.json()
        assert candidate["answer"] == answer_text
        assert candidate["status"] == "pending"
        candidate_id = candidate["id"]

        # Reviewer (admin) approves the candidate
        reviewer_login = _login(client, "admin", "tickets.api.reviewer")
        csrf = str(reviewer_login["csrf_token"])
        approve_resp = client.post(
            f"/api/v1/candidates/{candidate_id}/approve",
            headers={"X-CSRF-Token": csrf},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "published"
    finally:
        _restore_review_service_embeddings(original)


def test_submit_answer_missing_csrf_returns_403(client: TestClient) -> None:
    _login(client, "user", "tickets.api.owner")
    ticket_id = _seed_ticket(client, status=TicketStatus.IN_PROGRESS)
    resp = client.post(
        f"/api/v1/tickets/{ticket_id}/answers",
        json={"answer": "test"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "CSRF_INVALID"
