from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowagent.tickets.domain.models import (
    CandidateStatus,
    KnowledgeCandidate,
    ReplyAuthorRole,
    Ticket,
    TicketPriority,
    TicketReply,
    TicketStatus,
    TicketTransition,
)


class TicketView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    system_id: UUID
    requester_id: UUID
    source_run_id: UUID
    assignee_id: UUID | None = None
    status: TicketStatus
    priority: TicketPriority
    title: str
    question: str
    normalized_question: str
    occurrence_count: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_ticket(cls, ticket: Ticket) -> TicketView:
        return cls(
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
            occurrence_count=ticket.occurrence_count,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )


class TicketReplyView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    ticket_id: UUID
    system_id: UUID
    author_id: UUID
    author_role: ReplyAuthorRole
    body: str
    created_at: datetime

    @classmethod
    def from_reply(cls, reply: TicketReply) -> TicketReplyView:
        return cls(
            id=reply.id,
            ticket_id=reply.ticket_id,
            system_id=reply.system_id,
            author_id=reply.author_id,
            author_role=reply.author_role,
            body=reply.body,
            created_at=reply.created_at,
        )


class TicketTransitionView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    ticket_id: UUID
    system_id: UUID
    actor_id: UUID
    from_status: TicketStatus | None
    to_status: TicketStatus
    action: str
    created_at: datetime

    @classmethod
    def from_transition(cls, transition: TicketTransition) -> TicketTransitionView:
        return cls(
            id=transition.id,
            ticket_id=transition.ticket_id,
            system_id=transition.system_id,
            actor_id=transition.actor_id,
            from_status=transition.from_status,
            to_status=transition.to_status,
            action=transition.action,
            created_at=transition.created_at,
        )


class KnowledgeCandidateView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    ticket_id: UUID
    system_id: UUID
    answer: str
    author_id: UUID
    reviewer_id: UUID | None = None
    status: CandidateStatus
    knowledge_source_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_candidate(cls, candidate: KnowledgeCandidate) -> KnowledgeCandidateView:
        return cls(
            id=candidate.id,
            ticket_id=candidate.ticket_id,
            system_id=candidate.system_id,
            answer=candidate.answer,
            author_id=candidate.author_id,
            reviewer_id=candidate.reviewer_id,
            status=candidate.status,
            knowledge_source_id=candidate.knowledge_source_id,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        )


# Request models


class AssignTicketRequest(BaseModel):
    assignee_id: UUID


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class CloseTicketRequest(BaseModel):
    body: str | None = Field(default=None, max_length=10000)


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)


class TicketPage(BaseModel):
    items: list[TicketView]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
