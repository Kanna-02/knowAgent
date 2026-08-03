from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from knowagent.common.errors import ConflictError, NotFoundError, ValidationError
from knowagent.tickets.domain.models import CandidateStatus, KnowledgeCandidate
from knowagent.tickets.ports import TicketRepository

ANSWER_MAX_LENGTH = 10_000


class KnowledgeReviewService:
    """Bridges ticket answers into the knowledge base via review.

    The assignee submits an answer which becomes a pending
    :class:`KnowledgeCandidate`. A reviewer then approves or rejects it.
    Approval creates a TICKET-type knowledge source plus a single published
    knowledge chunk and marks the candidate approved, so the answer enters the
    knowledge base only after explicit review (AC-007). Unapproved answers
    never become retrieval candidates: the candidate stays PENDING or becomes
    REJECTED, and no knowledge chunk is created until approval.

    The candidate record itself (with ``reviewer_id`` and ``status``) serves as
    the audit trail for the review decision; ticket status transitions are the
    responsibility of :class:`TicketWorkflowService` and the orchestration layer.
    """

    def __init__(self, *, repository: TicketRepository) -> None:
        self._repository = repository

    def submit_answer(
        self,
        *,
        ticket_id: UUID,
        author_id: UUID,
        answer: str,
        now: datetime,
    ) -> KnowledgeCandidate:
        if now.tzinfo is None:
            raise ValueError("submit time must be timezone-aware")
        trimmed = answer.strip()
        if not trimmed:
            raise ValidationError("TICKET_ANSWER_BLANK", "工单答案不能为空")
        if len(trimmed) > ANSWER_MAX_LENGTH:
            raise ValidationError("TICKET_ANSWER_TOO_LONG", "工单答案超出最大长度")
        ticket = self._repository.lock_ticket(ticket_id=ticket_id)
        if ticket is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        existing = self._repository.get_pending_candidate_by_ticket(ticket_id=ticket_id)
        if existing is not None:
            raise ConflictError(
                "TICKET_CANDIDATE_EXISTS",
                "工单已有待审核答案，请先审核或退回后再提交",
            )
        candidate = self._repository.add_candidate(
            KnowledgeCandidate(
                id=uuid4(),
                ticket_id=ticket_id,
                system_id=ticket.system_id,
                answer=trimmed,
                author_id=author_id,
                reviewer_id=None,
                status=CandidateStatus.PENDING,
                knowledge_source_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        return candidate

    def approve(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate:
        if now.tzinfo is None:
            raise ValueError("approve time must be timezone-aware")
        candidate = self._repository.get_candidate(candidate_id=candidate_id)
        if candidate is None:
            raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
        if candidate.status is not CandidateStatus.PENDING:
            raise ConflictError(
                "KNOWLEDGE_CANDIDATE_NOT_PENDING",
                "只能审核待处理的知识候选",
            )
        knowledge_source_id = self._repository.create_ticket_knowledge_source(
            system_id=candidate.system_id,
            ticket_id=candidate.ticket_id,
            now=now,
        )
        self._repository.create_published_chunk(
            system_id=candidate.system_id,
            source_id=knowledge_source_id,
            text=candidate.answer,
            now=now,
        )
        approved = self._repository.approve_candidate(
            candidate_id=candidate_id,
            reviewer_id=reviewer_id,
            knowledge_source_id=knowledge_source_id,
            now=now,
        )
        return approved

    def reject(
        self,
        *,
        candidate_id: UUID,
        reviewer_id: UUID,
        now: datetime,
    ) -> KnowledgeCandidate:
        if now.tzinfo is None:
            raise ValueError("reject time must be timezone-aware")
        candidate = self._repository.get_candidate(candidate_id=candidate_id)
        if candidate is None:
            raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
        if candidate.status is not CandidateStatus.PENDING:
            raise ConflictError(
                "KNOWLEDGE_CANDIDATE_NOT_PENDING",
                "只能审核待处理的知识候选",
            )
        rejected = self._repository.reject_candidate(
            candidate_id=candidate_id,
            reviewer_id=reviewer_id,
            now=now,
        )
        return rejected

    def get_candidate(self, *, candidate_id: UUID) -> KnowledgeCandidate | None:
        return self._repository.get_candidate(candidate_id=candidate_id)

    def get_pending_candidate_by_ticket(self, *, ticket_id: UUID) -> KnowledgeCandidate | None:
        return self._repository.get_pending_candidate_by_ticket(ticket_id=ticket_id)
