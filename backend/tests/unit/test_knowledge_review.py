from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.tickets.application.review import KnowledgeReviewService
from knowagent.tickets.domain.models import (
    CandidateStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from knowagent.tickets.infrastructure.sqlalchemy_models import TicketRecord
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

NOW = datetime(2026, 8, 3, 16, 0, tzinfo=UTC)


def make_ticket(
    *,
    system_id: UUID | None = None,
    requester_id: UUID | None = None,
    assignee_id: UUID | None = None,
    status: TicketStatus = TicketStatus.IN_PROGRESS,
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
        title="ESB 如何配置未知参数？",
        question="ESB 如何配置未知参数？",
        normalized_question="esb 如何配置未知参数？".casefold(),
        deduplication_key="dummy-dedup-key",
        occurrence_count=1,
        created_at=now,
        updated_at=now,
    )


def setup_engine() -> object:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def setup_review(
    session: Session,
) -> tuple[KnowledgeReviewService, SqlAlchemyTicketRepository]:
    repository = SqlAlchemyTicketRepository(session)
    return KnowledgeReviewService(repository=repository), repository


def _create_ticket(session: Session, **kwargs: object) -> Ticket:
    ticket = make_ticket(**kwargs)
    session.add(
        TicketRecord(
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
    )
    session.flush()
    return ticket


def test_submit_answer_creates_pending_candidate_and_blocks_duplicate() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, repository = setup_review(session)
        requester_id = uuid4()
        ticket = _create_ticket(session, requester_id=requester_id)
        author_id = uuid4()

        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="参数名改了，请用新名", now=NOW
        )

        assert candidate.status is CandidateStatus.PENDING
        assert candidate.reviewer_id is None
        assert candidate.knowledge_source_id is None
        assert candidate.author_id == author_id

        pending = review.get_pending_candidate_by_ticket(ticket_id=ticket.id)
        assert pending is not None
        assert pending.id == candidate.id

        with pytest.raises(Exception, match="已有待审核答案"):
            review.submit_answer(ticket_id=ticket.id, author_id=author_id, answer="另一份", now=NOW)


def test_approve_creates_knowledge_source_and_published_chunk() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        author_id = uuid4()
        reviewer_id = uuid4()
        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="答案正文", now=NOW
        )

        approved = review.approve(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)

        assert approved.status is CandidateStatus.APPROVED
        assert approved.reviewer_id == reviewer_id
        assert approved.knowledge_source_id is not None

        source_id = approved.knowledge_source_id
        assert source_id is not None
        _assert_ticket_knowledge_source(
            session,
            source_id=source_id,
            system_id=ticket.system_id,
            ticket_id=ticket.id,
        )
        _assert_published_chunk(
            session,
            source_id=source_id,
            system_id=ticket.system_id,
            text="答案正文",
        )


def test_reject_marks_candidate_rejected_without_creating_knowledge() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        author_id = uuid4()
        reviewer_id = uuid4()
        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="答案正文", now=NOW
        )

        rejected = review.reject(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)

        assert rejected.status is CandidateStatus.REJECTED
        assert rejected.reviewer_id == reviewer_id
        assert rejected.knowledge_source_id is None
        _assert_no_knowledge_source_for_ticket(session, ticket_id=ticket.id)


def test_approve_non_pending_candidate_raises_conflict() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        author_id = uuid4()
        reviewer_id = uuid4()
        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="答案正文", now=NOW
        )
        review.reject(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)

        with pytest.raises(Exception, match="待处理"):
            review.approve(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)


def test_re_submit_after_rejection_creates_new_pending_candidate() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        author_id = uuid4()
        reviewer_id = uuid4()
        first = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="第一稿", now=NOW
        )
        review.reject(candidate_id=first.id, reviewer_id=reviewer_id, now=NOW)

        second = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="第二稿", now=NOW
        )

        assert second.id != first.id
        assert second.status is CandidateStatus.PENDING
        approved = review.approve(candidate_id=second.id, reviewer_id=reviewer_id, now=NOW)
        assert approved.status is CandidateStatus.APPROVED
        _assert_published_chunk(
            session,
            source_id=approved.knowledge_source_id,
            system_id=ticket.system_id,
            text="第二稿",
        )


def test_get_pending_candidate_returns_none_after_approval() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        author_id = uuid4()
        reviewer_id = uuid4()
        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="答案正文", now=NOW
        )
        review.approve(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)
        assert review.get_pending_candidate_by_ticket(ticket_id=ticket.id) is None


def test_submit_answer_to_unknown_ticket_raises_not_found() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        with pytest.raises(Exception, match="工单不存在"):
            review.submit_answer(ticket_id=uuid4(), author_id=uuid4(), answer="正文", now=NOW)


def test_submit_answer_blank_raises_validation_error() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        ticket = _create_ticket(session)
        with pytest.raises(Exception, match="不能为空"):
            review.submit_answer(ticket_id=ticket.id, author_id=uuid4(), answer="   ", now=NOW)


def test_approve_unknown_candidate_raises_not_found() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        with pytest.raises(Exception, match="知识候选不存在"):
            review.approve(candidate_id=uuid4(), reviewer_id=uuid4(), now=NOW)


def test_approve_preserves_ticket_system_isolation() -> None:
    engine = setup_engine()
    with Session(engine) as session:
        review, _ = setup_review(session)
        system_id = uuid4()
        ticket = _create_ticket(session, system_id=system_id)
        author_id = uuid4()
        reviewer_id = uuid4()
        candidate = review.submit_answer(
            ticket_id=ticket.id, author_id=author_id, answer="答案", now=NOW
        )
        approved = review.approve(candidate_id=candidate.id, reviewer_id=reviewer_id, now=NOW)
        assert approved.system_id == system_id
        assert approved.knowledge_source_id is not None
        _assert_ticket_knowledge_source(
            session,
            source_id=approved.knowledge_source_id,
            system_id=system_id,
            ticket_id=ticket.id,
        )


def _assert_ticket_knowledge_source(
    session: Session,
    *,
    source_id: UUID,
    system_id: UUID,
    ticket_id: UUID,
) -> None:
    from knowagent.common.lifecycle import PublicationStatus
    from knowagent.knowledge.domain.models import KnowledgeSourceType
    from knowagent.knowledge.infrastructure.sqlalchemy_models import (
        KnowledgeSourceRecord,
    )

    record = session.get(KnowledgeSourceRecord, source_id)
    assert record is not None
    assert record.system_id == system_id
    assert record.source_type is KnowledgeSourceType.TICKET
    assert record.publish_status is PublicationStatus.PUBLISHED
    assert record.ticket_id == ticket_id


def _assert_published_chunk(
    session: Session,
    *,
    source_id: UUID,
    system_id: UUID,
    text: str,
) -> None:
    from knowagent.common.lifecycle import PublicationStatus
    from knowagent.knowledge.infrastructure.sqlalchemy_models import (
        KnowledgeChunkRecord,
    )

    records = session.scalars(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.source_id == source_id,
            KnowledgeChunkRecord.system_id == system_id,
        )
    ).all()
    assert len(records) == 1
    assert records[0].publish_status is PublicationStatus.PUBLISHED
    assert records[0].text == text


def _assert_no_knowledge_source_for_ticket(
    session: Session,
    *,
    ticket_id: UUID,
) -> None:
    from knowagent.knowledge.infrastructure.sqlalchemy_models import (
        KnowledgeSourceRecord,
    )

    records = session.scalars(
        select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.ticket_id == ticket_id)
    ).all()
    assert records == []
