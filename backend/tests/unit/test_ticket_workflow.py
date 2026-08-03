from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.tickets.application.workflow import TicketWorkflowService
from knowagent.tickets.domain.models import (
    ReplyAuthorRole,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from knowagent.tickets.infrastructure.sqlalchemy_repository import SqlAlchemyTicketRepository

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)


def make_ticket(
    *,
    system_id: UUID | None = None,
    requester_id: UUID | None = None,
    assignee_id: UUID | None = None,
    status: TicketStatus = TicketStatus.OPEN,
    now: datetime = NOW,
) -> Ticket:
    return Ticket(
        id=uuid4(),
        system_id=system_id or uuid4(),
        requester_id=requester_id or uuid4(),
        source_run_id=uuid4(),
        assignee_id=assignee_id,
        status=status,
        priority=TicketPriority.NORMAL,
        title="ESB 参数无法识别怎么办？",
        question="ESB 参数无法识别怎么办？",
        normalized_question="esb 参数无法识别怎么办？".casefold(),
        deduplication_key="dummy-dedup-key",
        occurrence_count=1,
        created_at=now,
        updated_at=now,
    )


def setup_engine() -> object:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def setup_services(
    session: Session,
) -> tuple[TicketWorkflowService, SqlAlchemyTicketRepository]:
    repository = SqlAlchemyTicketRepository(session)
    return TicketWorkflowService(repository=repository), repository


def test_assign_persists_status_assignnee_and_transition() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, repository = setup_services(session)
        assignee_id = uuid4()
        actor_id = uuid4()
        requester_id = uuid4()
        system_id = uuid4()
        ticket = make_ticket(system_id=system_id, requester_id=requester_id)
        session.add(
            _ticket_record(ticket),
        )
        session.flush()

        result = workflow.assign(
            ticket_id=ticket.id,
            assignee_id=assignee_id,
            actor_id=actor_id,
            now=NOW,
        )

        assert result.status is TicketStatus.ASSIGNED
        assert result.assignee_id == assignee_id
        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert len(transitions) == 1
        assert transitions[0].from_status is TicketStatus.OPEN
        assert transitions[0].to_status is TicketStatus.ASSIGNED
        assert transitions[0].action == "assign"
        assert transitions[0].actor_id == actor_id


def test_start_transitions_assigned_to_in_progress_and_records_transition() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, repository = setup_services(session)
        actor_id = uuid4()
        assignee_id = uuid4()
        requester_id = uuid4()
        ticket = make_ticket(
            requester_id=requester_id,
            assignee_id=assignee_id,
            status=TicketStatus.ASSIGNED,
        )
        session.add(_ticket_record(ticket))
        session.flush()

        result = workflow.start(ticket_id=ticket.id, actor_id=actor_id, now=NOW)

        assert result.status is TicketStatus.IN_PROGRESS
        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert len(transitions) == 1
        assert transitions[0].from_status is TicketStatus.ASSIGNED
        assert transitions[0].to_status is TicketStatus.IN_PROGRESS


def test_reply_appends_message_with_requester_role_for_requester() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        requester_id = uuid4()
        ticket = make_ticket(requester_id=requester_id)
        session.add(_ticket_record(ticket))
        session.flush()

        reply, refreshed = workflow.reply(
            ticket_id=ticket.id,
            author_id=requester_id,
            body="补充：这个参数是新版本才有的",
            now=NOW,
        )

        assert reply.author_role is ReplyAuthorRole.REQUESTER
        assert refreshed.status is ticket.status
        assert len(workflow.list_replies(ticket_id=ticket.id)) == 1
        assert workflow.list_transitions(ticket_id=ticket.id) == ()


def test_reply_with_transition_changes_status_and_records_both() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        requester_id = uuid4()
        assignee_id = uuid4()
        ticket = make_ticket(
            requester_id=requester_id,
            assignee_id=assignee_id,
            status=TicketStatus.IN_PROGRESS,
        )
        session.add(_ticket_record(ticket))
        session.flush()

        body = "已修复，请确认"
        reply, result = workflow.reply(
            ticket_id=ticket.id,
            author_id=assignee_id,
            body=body,
            now=NOW,
            transition_to=TicketStatus.RESOLVED,
            action="resolve",
        )

        assert reply.author_role is ReplyAuthorRole.ASSIGNEE
        assert result.status is TicketStatus.RESOLVED
        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert len(transitions) == 1
        assert transitions[0].to_status is TicketStatus.RESOLVED
        assert transitions[0].action == "resolve"


def test_close_with_body_appends_reply_then_closes() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        requester_id = uuid4()
        assignee_id = uuid4()
        actor_id = uuid4()
        ticket = make_ticket(
            requester_id=requester_id,
            assignee_id=assignee_id,
            status=TicketStatus.RESOLVED,
        )
        session.add(_ticket_record(ticket))
        session.flush()

        result = workflow.close(
            ticket_id=ticket.id,
            actor_id=actor_id,
            now=NOW,
            body="确认已解决",
        )

        assert result.status is TicketStatus.CLOSED
        replies = workflow.list_replies(ticket_id=ticket.id)
        assert len(replies) == 1
        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert len(transitions) == 1
        assert transitions[0].to_status is TicketStatus.CLOSED


def test_close_without_body_just_closes() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        actor_id = uuid4()
        ticket = make_ticket(status=TicketStatus.RESOLVED)
        session.add(_ticket_record(ticket))
        session.flush()

        result = workflow.close(ticket_id=ticket.id, actor_id=actor_id, now=NOW)
        assert result.status is TicketStatus.CLOSED
        assert workflow.list_replies(ticket_id=ticket.id) == ()
        assert len(workflow.list_transitions(ticket_id=ticket.id)) == 1


def test_reopen_transitions_closed_to_open_and_records_transition() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        actor_id = uuid4()
        ticket = make_ticket(status=TicketStatus.CLOSED)
        session.add(_ticket_record(ticket))
        session.flush()

        result = workflow.reopen(ticket_id=ticket.id, actor_id=actor_id, now=NOW)

        assert result.status is TicketStatus.OPEN
        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert len(transitions) == 1
        assert transitions[0].from_status is TicketStatus.CLOSED
        assert transitions[0].to_status is TicketStatus.OPEN


def test_full_lifecycle_assign_start_resolve_close_reopen_records_all_transitions() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        requester_id = uuid4()
        assignee_id = uuid4()
        reviewer_id = uuid4()
        actor_id = uuid4()
        ticket = make_ticket(requester_id=requester_id)
        session.add(_ticket_record(ticket))
        session.flush()

        workflow.assign(ticket_id=ticket.id, assignee_id=assignee_id, actor_id=actor_id, now=NOW)
        workflow.start(ticket_id=ticket.id, actor_id=actor_id, now=NOW)
        workflow.reply(
            ticket_id=ticket.id,
            author_id=assignee_id,
            body="需要再补充一个测试",
            now=NOW,
            transition_to=TicketStatus.RESOLVED,
            action="resolve",
        )
        workflow.close(ticket_id=ticket.id, actor_id=reviewer_id, now=NOW)
        workflow.reopen(ticket_id=ticket.id, actor_id=reviewer_id, now=NOW)

        transitions = workflow.list_transitions(ticket_id=ticket.id)
        assert [t.to_status for t in transitions] == [
            TicketStatus.ASSIGNED,
            TicketStatus.IN_PROGRESS,
            TicketStatus.RESOLVED,
            TicketStatus.CLOSED,
            TicketStatus.OPEN,
        ]
        assert transitions[0].from_status is TicketStatus.OPEN
        assert transitions[-1].from_status is TicketStatus.CLOSED


def test_invalid_transition_raises_conflict() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        actor_id = uuid4()
        ticket = make_ticket(status=TicketStatus.OPEN)
        session.add(_ticket_record(ticket))
        session.flush()

        with pytest.raises(ConflictError, match="不允许"):
            workflow.start(ticket_id=ticket.id, actor_id=actor_id, now=NOW)

        resolved_ticket = make_ticket(status=TicketStatus.RESOLVED)
        session.add(_ticket_record(resolved_ticket))
        session.flush()
        with pytest.raises(ConflictError, match="不允许"):
            workflow.reopen(ticket_id=resolved_ticket.id, actor_id=actor_id, now=NOW)


def test_same_status_transition_raises_conflict() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        actor_id = uuid4()
        requester_id = uuid4()
        ticket = make_ticket(requester_id=requester_id, status=TicketStatus.OPEN)
        session.add(_ticket_record(ticket))
        session.flush()

        with pytest.raises(ConflictError, match="状态未变化"):
            workflow.reopen(ticket_id=ticket.id, actor_id=actor_id, now=NOW)


def test_assign_unknown_ticket_raises_not_found() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        with pytest.raises(NotFoundError, match="工单不存在"):
            workflow.assign(
                ticket_id=uuid4(),
                assignee_id=uuid4(),
                actor_id=uuid4(),
                now=NOW,
            )


def test_reply_blank_body_raises_validation_error() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        ticket = make_ticket()
        session.add(_ticket_record(ticket))
        session.flush()

        with pytest.raises(ValidationError, match="不能为空"):
            workflow.reply(ticket_id=ticket.id, author_id=uuid4(), body="   ", now=NOW)


def test_reply_too_long_raises_validation_error() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        ticket = make_ticket()
        session.add(_ticket_record(ticket))
        session.flush()

        with pytest.raises(ValidationError, match="超出最大长度"):
            workflow.reply(ticket_id=ticket.id, author_id=uuid4(), body="x" * 10_001, now=NOW)


def test_reply_non_requester_non_assignee_gets_reviewer_role() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        workflow, _ = setup_services(session)
        ticket = make_ticket(requester_id=uuid4())
        session.add(_ticket_record(ticket))
        session.flush()

        reviewer_id = uuid4()
        reply, _ = workflow.reply(
            ticket_id=ticket.id, author_id=reviewer_id, body="请补充日志", now=NOW
        )
        assert reply.author_role is ReplyAuthorRole.REVIEWER


def _ticket_record(ticket: Ticket) -> object:
    from knowagent.tickets.infrastructure.sqlalchemy_models import TicketRecord

    return TicketRecord(
        id=ticket.id,
        system_id=ticket.system_id,
        requester_id=ticket.requester_id,
        source_run_id=ticket.source_run_id,
        assignee_id=ticket.assignee_id,
        status=ticket.status,
        priority=ticket.priority,
        title=ticket.title,
        question=ticket.question,
        normalized_question=ticket.normalized_question,
        deduplication_key=ticket.deduplication_key,
        occurrence_count=ticket.occurrence_count,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )
