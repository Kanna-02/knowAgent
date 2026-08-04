from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import (
    EvidenceCandidateSummary,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
)
from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.tickets.application.refusal import RefusalTicketService
from knowagent.tickets.infrastructure.sqlalchemy_models import TicketOccurrenceRecord
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def make_decision(
    *,
    run_id: UUID | None = None,
    system_id: UUID | None = None,
    query: str = "ESB 如何配置未知参数？",
    outcome: EvidenceDecisionOutcome = EvidenceDecisionOutcome.INSUFFICIENT,
    candidates: tuple[EvidenceCandidateSummary, ...] = (),
) -> EvidenceDecision:
    if outcome is EvidenceDecisionOutcome.SUFFICIENT:
        reason_codes: tuple[EvidenceReasonCode, ...] = ()
    elif outcome is EvidenceDecisionOutcome.CONFLICTING:
        reason_codes = (EvidenceReasonCode.CONFLICTING_EVIDENCE,)
    else:
        reason_codes = (EvidenceReasonCode.NO_EVIDENCE,)
    return EvidenceDecision(
        id=uuid4(),
        run_id=run_id or uuid4(),
        system_id=system_id or uuid4(),
        query=query,
        normalized_query=query.casefold(),
        outcome=outcome,
        reason_codes=reason_codes,
        score=None,
        applied_score_threshold=0.015,
        policy_version="evidence-v1",
        candidates=candidates,
        degraded_reasons=(),
        decided_at=NOW,
    )


def service(session: Session) -> tuple[RefusalTicketService, SqlAlchemyTicketRepository]:
    repository = SqlAlchemyTicketRepository(session)
    return (
        RefusalTicketService(
            repository=repository,
            deduplication_window=timedelta(hours=24),
        ),
        repository,
    )


def test_create_from_refusal_persists_reason_and_open_ticket_atomically() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        requester_id = uuid4()
        decision = make_decision()

        ticket_id = tickets.create_from_refusal(
            decision=decision,
            requester_id=requester_id,
            now=NOW,
        )
        session.commit()

        stored_decision = repository.get_decision(run_id=decision.run_id)
        stored_ticket = repository.get_ticket(ticket_id=ticket_id)
        assert stored_decision is not None
        assert stored_decision.reason_codes == (EvidenceReasonCode.NO_EVIDENCE,)
        assert stored_decision.ticket_id == ticket_id
        assert stored_ticket is not None
        assert stored_ticket.requester_id == requester_id
        assert stored_ticket.occurrence_count == 1
        assert stored_ticket.status.value == "open"
        occurrences = repository.list_ticket_occurrences(ticket_id=ticket_id)
        assert len(occurrences) == 1
        assert occurrences[0].run_id == decision.run_id
        assert occurrences[0].requester_id == requester_id


def test_create_from_refusal_flushes_decision_before_occurrence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    insert_order: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_insert_order(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("INSERT INTO"):
            insert_order.append(statement.split()[2])

    with Session(engine) as session:
        tickets, _ = service(session)
        tickets.create_from_refusal(
            decision=make_decision(),
            requester_id=uuid4(),
            now=NOW,
        )

    assert insert_order.index("evidence_decisions") < insert_order.index("ticket_occurrences")


def test_create_from_refusal_replaying_run_returns_same_ticket_without_increment() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        decision = make_decision()
        requester_id = uuid4()

        first = tickets.create_from_refusal(decision=decision, requester_id=requester_id, now=NOW)
        replay = tickets.create_from_refusal(decision=decision, requester_id=requester_id, now=NOW)

        assert replay == first
        assert repository.get_ticket(ticket_id=first).occurrence_count == 1
        assert len(repository.list_ticket_occurrences(ticket_id=first)) == 1


def test_create_from_refusal_same_normalized_question_merges_within_window() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        system_id = uuid4()
        first_decision = make_decision(system_id=system_id, query="  ESB 如何配置？ ")
        second_decision = make_decision(system_id=system_id, query="esb   如何配置？")

        first_requester_id = uuid4()
        second_requester_id = uuid4()
        first = tickets.create_from_refusal(
            decision=first_decision,
            requester_id=first_requester_id,
            now=NOW,
        )
        second = tickets.create_from_refusal(
            decision=second_decision,
            requester_id=second_requester_id,
            now=NOW + timedelta(hours=1),
        )

        assert second == first
        assert repository.get_ticket(ticket_id=second).occurrence_count == 2
        assert repository.get_decision(run_id=second_decision.run_id).ticket_id == first
        occurrences = repository.list_ticket_occurrences(ticket_id=first)
        assert {occurrence.requester_id for occurrence in occurrences} == {
            first_requester_id,
            second_requester_id,
        }


def test_create_from_refusal_merges_across_fixed_bucket_boundary_within_window() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        system_id = uuid4()
        boundary = datetime(2026, 8, 4, tzinfo=UTC)

        first = tickets.create_from_refusal(
            decision=make_decision(system_id=system_id),
            requester_id=uuid4(),
            now=boundary - timedelta(minutes=1),
        )
        second = tickets.create_from_refusal(
            decision=make_decision(system_id=system_id),
            requester_id=uuid4(),
            now=boundary + timedelta(minutes=1),
        )

        assert second == first
        assert repository.get_ticket(ticket_id=first).occurrence_count == 2


def test_create_from_refusal_after_rolling_window_creates_new_ticket() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)
        system_id = uuid4()

        first = tickets.create_from_refusal(
            decision=make_decision(system_id=system_id),
            requester_id=uuid4(),
            now=NOW,
        )
        second = tickets.create_from_refusal(
            decision=make_decision(system_id=system_id),
            requester_id=uuid4(),
            now=NOW + timedelta(hours=24, seconds=1),
        )

        assert second != first


def test_create_from_refusal_same_question_in_different_system_creates_separate_ticket() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)

        first = tickets.create_from_refusal(
            decision=make_decision(system_id=uuid4()),
            requester_id=uuid4(),
            now=NOW,
        )
        second = tickets.create_from_refusal(
            decision=make_decision(system_id=uuid4()),
            requester_id=uuid4(),
            now=NOW,
        )

        assert second != first


def test_record_sufficient_decision_does_not_create_ticket() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        decision = make_decision(outcome=EvidenceDecisionOutcome.SUFFICIENT)

        tickets.record_sufficient(decision=decision)

        stored = repository.get_decision(run_id=decision.run_id)
        assert stored is not None
        assert stored.ticket_id is None
        assert repository.count_tickets() == 0


def test_record_sufficient_replay_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        decision = make_decision(outcome=EvidenceDecisionOutcome.SUFFICIENT)

        tickets.record_sufficient(decision=decision)
        tickets.record_sufficient(decision=decision)

        assert repository.get_decision(run_id=decision.run_id).id == decision.id
        assert repository.count_tickets() == 0


def test_record_sufficient_replay_with_changed_payload_raises_conflict() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)
        decision = make_decision(outcome=EvidenceDecisionOutcome.SUFFICIENT)
        tickets.record_sufficient(decision=decision)

        with pytest.raises(ConflictError, match="判定内容不一致"):
            tickets.record_sufficient(
                decision=make_decision(
                    run_id=decision.run_id,
                    system_id=decision.system_id,
                    query="不同问题",
                    outcome=EvidenceDecisionOutcome.SUFFICIENT,
                )
            )


def test_create_from_refusal_rejects_sufficient_decision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)

        with pytest.raises(ValidationError, match="只有证据不足或冲突"):
            tickets.create_from_refusal(
                decision=make_decision(outcome=EvidenceDecisionOutcome.SUFFICIENT),
                requester_id=uuid4(),
                now=NOW,
            )

        assert repository.count_tickets() == 0


def test_create_from_conflict_round_trips_candidate_summary_and_reason() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, repository = service(session)
        candidate = EvidenceCandidateSummary(
            chunk_id=uuid4(),
            source_id=uuid4(),
            source_name="ESB 手册.pdf",
            source_version="4",
            fused_score=0.031,
            channels=("keyword", "vector"),
        )
        decision = make_decision(
            outcome=EvidenceDecisionOutcome.CONFLICTING,
            candidates=(candidate,),
        )

        ticket_id = tickets.create_from_refusal(
            decision=decision,
            requester_id=uuid4(),
            now=NOW,
        )

        stored = repository.get_decision(run_id=decision.run_id)
        assert stored.outcome is EvidenceDecisionOutcome.CONFLICTING
        assert stored.reason_codes == (EvidenceReasonCode.CONFLICTING_EVIDENCE,)
        assert stored.ticket_id == ticket_id
        assert stored.candidates == (candidate,)


def test_service_with_non_positive_deduplication_window_raises_value_error() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as session:
        repository = SqlAlchemyTicketRepository(session)

        with pytest.raises(ValueError, match="must be positive"):
            RefusalTicketService(
                repository=repository,
                deduplication_window=timedelta(0),
            )


def test_record_sufficient_rejects_refusal_decision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)

        with pytest.raises(ValidationError, match="不能记录为充分证据"):
            tickets.record_sufficient(decision=make_decision())


def test_record_sufficient_conflicts_with_existing_refusal_decision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)
        refusal = make_decision()
        tickets.create_from_refusal(decision=refusal, requester_id=uuid4(), now=NOW)

        with pytest.raises(ConflictError, match="已有不同判定"):
            tickets.record_sufficient(
                decision=make_decision(
                    run_id=refusal.run_id,
                    system_id=refusal.system_id,
                    outcome=EvidenceDecisionOutcome.SUFFICIENT,
                )
            )


def test_create_from_refusal_with_naive_timestamp_raises_value_error() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)

        with pytest.raises(ValueError, match="timezone-aware"):
            tickets.create_from_refusal(
                decision=make_decision(),
                requester_id=uuid4(),
                now=NOW.replace(tzinfo=None),
            )


def test_create_from_refusal_conflicts_with_existing_sufficient_decision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)
        sufficient = make_decision(outcome=EvidenceDecisionOutcome.SUFFICIENT)
        tickets.record_sufficient(decision=sufficient)

        with pytest.raises(ConflictError, match="已有非拒答判定"):
            tickets.create_from_refusal(
                decision=make_decision(
                    run_id=sufficient.run_id,
                    system_id=sufficient.system_id,
                ),
                requester_id=uuid4(),
                now=NOW,
            )


def test_create_from_refusal_replay_with_different_requester_raises_conflict() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tickets, _ = service(session)
        decision = make_decision()
        tickets.create_from_refusal(decision=decision, requester_id=uuid4(), now=NOW)

        with pytest.raises(ConflictError, match="提问人不一致"):
            tickets.create_from_refusal(
                decision=decision,
                requester_id=uuid4(),
                now=NOW,
            )


def test_ticket_occurrence_uses_composite_system_foreign_key() -> None:
    constrained_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in TicketOccurrenceRecord.__table__.foreign_key_constraints
    }

    assert ("ticket_id", "system_id") in constrained_columns


def test_increment_ticket_occurrence_for_unknown_ticket_raises_not_found() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _, repository = service(session)

        with pytest.raises(NotFoundError, match="工单不存在"):
            repository.increment_ticket_occurrence(ticket_id=uuid4(), now=NOW)
