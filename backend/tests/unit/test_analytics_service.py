from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import EvidenceDecisionOutcome
from knowagent.agent.infrastructure.sqlalchemy_models import (
    ConversationMessageRecord,
    ConversationRecord,
    EvidenceDecisionRecord,
)
from knowagent.analytics.application.analytics_service import AnalyticsService
from knowagent.analytics.domain.models import AnalyticsWindow, GapSource
from knowagent.common.errors import ValidationError
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.tickets.infrastructure.sqlalchemy_models import (
    TicketOccurrenceRecord,
    TicketRecord,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
SYSTEM_ID = uuid4()
ACCOUNT_ID = uuid4()
RUN_ID_1 = uuid4()
RUN_ID_2 = uuid4()


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_system_and_account(session: Session) -> None:
    from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
    from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
    from knowagent.systems.domain.models import BusinessSystemStatus
    from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord

    session.add(
        AccountRecord(
            id=ACCOUNT_ID,
            username="owner",
            display_name="Owner",
            password_hash="dummy",
            role=AccountRole.SYSTEM_OWNER,
            source=AccountSource.ADMIN_CREATED,
            status=AccountStatus.ACTIVE,
            must_change_password=False,
            session_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        BusinessSystemRecord(
            id=SYSTEM_ID,
            code="TEST",
            name="Test System",
            description="test",
            status=BusinessSystemStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.flush()


def _seed_conversation(session: Session, *, question: str, created_at: datetime) -> None:
    conv_id = uuid4()
    session.add(
        ConversationRecord(
            id=conv_id,
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title=question,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.add(
        ConversationMessageRecord(
            id=uuid4(),
            conversation_id=conv_id,
            system_id=SYSTEM_ID,
            sequence_number=1,
            role="user",
            content=question,
            intent="standalone",
            rewritten_query=None,
            rewrite_prompt_version=None,
            created_at=created_at,
        )
    )
    session.flush()


def _seed_evidence_decision(
    session: Session,
    *,
    run_id: uuid4,
    query: str,
    normalized_query: str,
    outcome: EvidenceDecisionOutcome,
    created_at: datetime,
) -> None:
    session.add(
        EvidenceDecisionRecord(
            id=uuid4(),
            run_id=run_id,
            system_id=SYSTEM_ID,
            ticket_id=None,
            query=query,
            normalized_query=normalized_query,
            outcome=outcome,
            reason_codes=["insufficient"],
            score=0.1,
            applied_score_threshold=0.5,
            policy_version="v1",
            retrieval_profile_name=None,
            retrieval_profile_version=None,
            candidate_summaries=[],
            degraded_reasons=[],
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.flush()


def _seed_ticket(
    session: Session,
    *,
    title: str,
    question: str,
    normalized_question: str,
    status: str,
    source_run_id: uuid4,
    occurrence_count: int = 1,
    created_at: datetime,
) -> uuid4:
    ticket_id = uuid4()
    session.add(
        TicketRecord(
            id=ticket_id,
            system_id=SYSTEM_ID,
            requester_id=ACCOUNT_ID,
            source_run_id=source_run_id,
            assignee_id=None,
            status=status,
            priority="normal",
            title=title,
            question=question,
            normalized_question=normalized_question,
            deduplication_key=f"dedup-{normalized_question}",
            occurrence_count=occurrence_count,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.add(
        TicketOccurrenceRecord(
            id=uuid4(),
            ticket_id=ticket_id,
            system_id=SYSTEM_ID,
            run_id=source_run_id,
            requester_id=ACCOUNT_ID,
            question=question,
            created_at=created_at,
        )
    )
    session.flush()
    return ticket_id


class TestAnalyticsService:
    def test_system_overview_counts_questions_refusals_and_tickets(self) -> None:
        with _create_session() as session:
            _seed_system_and_account(session)
            _seed_conversation(
                session, question="如何执行迁移？", created_at=NOW - timedelta(days=10)
            )
            _seed_conversation(
                session, question="如何重置密码？", created_at=NOW - timedelta(days=5)
            )
            _seed_evidence_decision(
                session,
                run_id=RUN_ID_1,
                query="如何执行迁移？",
                normalized_query="如何执行迁移",
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                created_at=NOW - timedelta(days=9),
            )
            ticket_id = _seed_ticket(
                session,
                title="如何执行迁移",
                question="如何执行迁移？",
                normalized_question="如何执行迁移",
                status="open",
                source_run_id=RUN_ID_1,
                created_at=NOW - timedelta(days=8),
            )
            from knowagent.knowledge.infrastructure.sqlalchemy_models import (
                KnowledgeSourceRecord,
            )

            _seed_ticket(
                session,
                title="如何重置密码",
                question="如何重置密码？",
                normalized_question="如何重置密码",
                status="closed",
                source_run_id=RUN_ID_2,
                created_at=NOW - timedelta(days=4),
            )
            session.add(
                KnowledgeSourceRecord(
                    id=uuid4(),
                    system_id=SYSTEM_ID,
                    ticket_id=ticket_id,
                    source_type="TICKET",
                    document_version_id=None,
                    publish_status="DRAFT",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

            service = AnalyticsService(session)
            window = AnalyticsWindow(
                started_at=NOW - timedelta(days=30),
                ended_at=NOW,
            )
            overview = service.get_system_overview(system_id=SYSTEM_ID, window=window)
            assert overview.question_count == 2
            assert overview.refusal_count == 1
            assert overview.open_ticket_count == 1
            assert overview.resolved_ticket_count == 1
            assert overview.total_ticket_count == 2

    def test_frequent_questions_groups_by_normalized_question(self) -> None:
        with _create_session() as session:
            _seed_system_and_account(session)
            _seed_evidence_decision(
                session,
                run_id=RUN_ID_1,
                query="如何执行数据库迁移？",
                normalized_query="如何执行数据库迁移",
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                created_at=NOW - timedelta(days=5),
            )
            _seed_ticket(
                session,
                title="迁移数据库",
                question="如何执行数据库迁移？",
                normalized_question="如何执行数据库迁移",
                status="open",
                source_run_id=RUN_ID_1,
                occurrence_count=3,
                created_at=NOW - timedelta(days=3),
            )

            service = AnalyticsService(session)
            window = AnalyticsWindow(
                started_at=NOW - timedelta(days=30),
                ended_at=NOW,
            )
            items = service.list_frequent_questions(system_id=SYSTEM_ID, window=window, top_n=10)
            assert len(items) == 1
            item = items[0]
            assert item.normalized_question == "如何执行数据库迁移"
            assert item.occurrence_count == 3
            assert item.refusal_count == 1
            assert item.ticket_count == 1

    def test_knowledge_gaps_merges_refusals_and_unsolved_tickets(self) -> None:
        with _create_session() as session:
            _seed_system_and_account(session)
            _seed_evidence_decision(
                session,
                run_id=RUN_ID_1,
                query="如何执行迁移？",
                normalized_query="如何执行迁移",
                outcome=EvidenceDecisionOutcome.INSUFFICIENT,
                created_at=NOW - timedelta(days=5),
            )
            _seed_ticket(
                session,
                title="迁移",
                question="如何执行迁移？",
                normalized_question="如何执行迁移",
                status="open",
                source_run_id=RUN_ID_1,
                created_at=NOW - timedelta(days=3),
            )

            service = AnalyticsService(session)
            window = AnalyticsWindow(
                started_at=NOW - timedelta(days=30),
                ended_at=NOW,
            )
            gaps = service.list_knowledge_gaps(system_id=SYSTEM_ID, window=window, top_n=10)
            assert len(gaps) == 1
            gap = gaps[0]
            assert gap.normalized_question == "如何执行迁移"
            assert gap.gap_source is GapSource.REFUSAL
            assert gap.occurrence_count >= 1

    def test_analytics_window_validates_time_awareness(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AnalyticsWindow(
                started_at=datetime(2026, 8, 1, 0, 0),
                ended_at=NOW,
            )

    def test_analytics_window_validates_order(self) -> None:
        with pytest.raises(ValueError, match="must not exceed"):
            AnalyticsWindow(
                started_at=NOW + timedelta(days=1),
                ended_at=NOW,
            )

    def test_top_n_validation(self) -> None:
        with _create_session() as session:
            service = AnalyticsService(session)
            window = AnalyticsWindow(started_at=NOW - timedelta(days=1), ended_at=NOW)
            with pytest.raises(ValueError, match="positive"):
                service.list_frequent_questions(system_id=SYSTEM_ID, window=window, top_n=0)
            with pytest.raises(ValueError, match="must not exceed"):
                service.list_knowledge_gaps(system_id=SYSTEM_ID, window=window, top_n=101)
