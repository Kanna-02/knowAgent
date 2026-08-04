from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.application.answer_snapshots import AnswerSnapshotService
from knowagent.agent.domain.models import (
    AnswerSnapshot,
    CitationSnapshot,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    VerifiedAnswer,
    VerifiedClaim,
)
from knowagent.agent.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAnswerSnapshotRepository,
)
from knowagent.common.errors import ConflictError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

NOW = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def make_decision(*, run_id: UUID | None = None, system_id: UUID | None = None) -> EvidenceDecision:
    return EvidenceDecision(
        id=uuid4(),
        run_id=run_id or uuid4(),
        system_id=system_id or uuid4(),
        query="ESB 参数如何配置？",
        normalized_query="esb 参数如何配置？",
        outcome=EvidenceDecisionOutcome.SUFFICIENT,
        reason_codes=(),
        score=0.03,
        applied_score_threshold=0.015,
        policy_version="evidence-v1",
        candidates=(),
        degraded_reasons=(),
        decided_at=NOW,
    )


def make_answer(*, ticket_id: UUID | None = None) -> VerifiedAnswer:
    locator = SourceLocator(
        source_type=SourceType.TICKET,
        block_index=0,
        ticket_id=ticket_id or uuid4(),
    )
    return VerifiedAnswer(
        text="请使用参数 new_name。",
        claims=(VerifiedClaim(rank=1, text="请使用参数 new_name。", citation_ranks=(1,)),),
        citations=(
            CitationSnapshot(
                rank=1,
                claim_rank=1,
                chunk_id=uuid4(),
                source_id=uuid4(),
                source_name="工单：ESB 参数如何配置？",
                source_version="candidate-1",
                quoted_text="请使用参数 new_name。",
                locators=(locator,),
            ),
        ),
        model="qwen-test",
        prompt_version="grounded-answer-v1",
    )


def setup_service(session: Session) -> AnswerSnapshotService:
    return AnswerSnapshotService(repository=SqlAlchemyAnswerSnapshotRepository(session))


def test_record_and_read_preserves_immutable_ticket_citation_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        decision = make_decision()
        SqlAlchemyTicketRepository(session).add_decision(decision=decision, ticket_id=None)
        answer = make_answer()

        stored = setup_service(session).record(
            decision=decision,
            answer=answer,
            degraded_reasons=("VECTOR_UNAVAILABLE",),
            now=NOW,
        )
        session.commit()
        loaded = setup_service(session).get_by_run(
            system_id=decision.system_id,
            run_id=decision.run_id,
        )

        assert loaded == stored
        assert loaded is not None
        assert loaded.answer == answer
        assert loaded.degraded_reasons == ("VECTOR_UNAVAILABLE",)
        assert loaded.answer.citations[0].locators[0].ticket_id is not None


def test_record_replay_is_idempotent_but_changed_snapshot_conflicts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        decision = make_decision()
        SqlAlchemyTicketRepository(session).add_decision(decision=decision, ticket_id=None)
        answer = make_answer()
        service = setup_service(session)

        first = service.record(decision=decision, answer=answer, degraded_reasons=(), now=NOW)
        replay = service.record(decision=decision, answer=answer, degraded_reasons=(), now=NOW)

        assert replay.id == first.id
        with pytest.raises(ConflictError, match="快照"):
            service.record(
                decision=decision,
                answer=VerifiedAnswer(
                    text="不同答案",
                    claims=answer.claims,
                    citations=answer.citations,
                    model=answer.model,
                    prompt_version=answer.prompt_version,
                ),
                degraded_reasons=(),
                now=NOW,
            )


def test_repository_unique_conflict_returns_existing_snapshot_for_service_comparison() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        decision = make_decision()
        SqlAlchemyTicketRepository(session).add_decision(decision=decision, ticket_id=None)
        answer = make_answer()
        service = setup_service(session)
        first = service.record(decision=decision, answer=answer, degraded_reasons=(), now=NOW)

        existing = SqlAlchemyAnswerSnapshotRepository(session).add_or_get(
            AnswerSnapshot(
                id=uuid4(),
                run_id=decision.run_id,
                system_id=decision.system_id,
                answer=answer,
                degraded_reasons=(),
                created_at=NOW,
            )
        )

        assert existing == first


def test_get_by_run_hides_snapshot_from_another_system() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        decision = make_decision()
        SqlAlchemyTicketRepository(session).add_decision(decision=decision, ticket_id=None)
        service = setup_service(session)
        service.record(decision=decision, answer=make_answer(), degraded_reasons=(), now=NOW)

        assert service.get_by_run(system_id=uuid4(), run_id=decision.run_id) is None
