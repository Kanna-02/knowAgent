from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from sqlalchemy.orm import Session

from knowagent.common.errors import (
    AuthorizationError,
    NotFoundError,
)
from knowagent.identity.api.access import require_system_access as _require_shared
from knowagent.identity.api.access import visible_system_ids as _visible_ids_shared
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
)
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider
from knowagent.tickets.api.schemas import (
    AssignTicketRequest,
    CloseTicketRequest,
    KnowledgeCandidateView,
    ReplyRequest,
    SubmitAnswerRequest,
    TicketPage,
    TicketReplyView,
    TicketTransitionView,
    TicketView,
)
from knowagent.tickets.application.review import KnowledgeReviewService
from knowagent.tickets.application.workflow import TicketWorkflowService
from knowagent.tickets.domain.models import (  # noqa: F401  TicketStatus used in Query()
    Ticket,
    TicketStatus,
)
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

router = APIRouter()


@router.get("/tickets", response_model=TicketPage)
def list_tickets(
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    system_id: Annotated[UUID | None, Query()] = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TicketPage:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    visible_systems = _visible_system_ids(context.account, database)
    if system_id is not None:
        if system_id not in visible_systems:
            raise AuthorizationError("SYSTEM_ACCESS_DENIED", "没有该业务系统的访问权限")
        target_systems = [system_id]
    else:
        target_systems = visible_systems
    if not target_systems:
        # No visible systems: return an empty page without hitting the
        # repository, so an account with zero visible systems cannot fall back
        # to an unfiltered full-table scan.
        return TicketPage(items=[], page=page, page_size=page_size, total=0)
    repository = SqlAlchemyTicketRepository(database)
    items, total = repository.list_tickets_page(
        system_ids=target_systems,
        status=ticket_status,
        page=page,
        page_size=page_size,
    )
    return TicketPage(
        items=[TicketView.from_ticket(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketView)
def get_ticket(
    ticket_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    return TicketView.from_ticket(ticket)


@router.get("/tickets/{ticket_id}/replies", response_model=list[TicketReplyView])
def list_ticket_replies(
    ticket_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> list[TicketReplyView]:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    repository = SqlAlchemyTicketRepository(database)
    replies = repository.list_replies(ticket_id=ticket_id)
    return [TicketReplyView.from_reply(reply) for reply in replies]


@router.get("/tickets/{ticket_id}/transitions", response_model=list[TicketTransitionView])
def list_ticket_transitions(
    ticket_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> list[TicketTransitionView]:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    repository = SqlAlchemyTicketRepository(database)
    transitions = repository.list_transitions(ticket_id=ticket_id)
    return [TicketTransitionView.from_transition(transition) for transition in transitions]


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=TicketView,
    status_code=status.HTTP_200_OK,
)
def assign_ticket(
    ticket_id: UUID,
    payload: AssignTicketRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    updated = service.assign(
        ticket_id=ticket_id,
        assignee_id=payload.assignee_id,
        actor_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.assign",
        object_id=ticket_id,
        system_id=ticket.system_id,
    )
    return TicketView.from_ticket(updated)


@router.post(
    "/tickets/{ticket_id}/start",
    response_model=TicketView,
    status_code=status.HTTP_200_OK,
)
def start_ticket(
    ticket_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    updated = service.start(
        ticket_id=ticket_id,
        actor_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.start",
        object_id=ticket_id,
        system_id=ticket.system_id,
    )
    return TicketView.from_ticket(updated)


@router.post(
    "/tickets/{ticket_id}/reply",
    response_model=TicketReplyView,
    status_code=status.HTTP_201_CREATED,
)
def reply_ticket(
    ticket_id: UUID,
    payload: ReplyRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketReplyView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    reply, _ = service.reply(
        ticket_id=ticket_id,
        author_id=context.account.id,
        body=payload.body,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.reply",
        object_id=reply.id,
        system_id=ticket.system_id,
    )
    return TicketReplyView.from_reply(reply)


@router.post(
    "/tickets/{ticket_id}/resolve",
    response_model=TicketView,
    status_code=status.HTTP_200_OK,
)
def resolve_ticket(
    ticket_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    updated = service.resolve(
        ticket_id=ticket_id,
        actor_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.resolve",
        object_id=ticket_id,
        system_id=ticket.system_id,
    )
    return TicketView.from_ticket(updated)


@router.post(
    "/tickets/{ticket_id}/close",
    response_model=TicketView,
    status_code=status.HTTP_200_OK,
)
def close_ticket(
    ticket_id: UUID,
    payload: CloseTicketRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    updated = service.close(
        ticket_id=ticket_id,
        actor_id=context.account.id,
        now=now,
        body=payload.body,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.close",
        object_id=ticket_id,
        system_id=ticket.system_id,
    )
    return TicketView.from_ticket(updated)


@router.post(
    "/tickets/{ticket_id}/reopen",
    response_model=TicketView,
    status_code=status.HTTP_200_OK,
)
def reopen_ticket(
    ticket_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> TicketView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    service = TicketWorkflowService(repository=SqlAlchemyTicketRepository(database))
    updated = service.reopen(
        ticket_id=ticket_id,
        actor_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.reopen",
        object_id=ticket_id,
        system_id=ticket.system_id,
    )
    return TicketView.from_ticket(updated)


@router.post(
    "/tickets/{ticket_id}/answers",
    response_model=KnowledgeCandidateView,
    status_code=status.HTTP_201_CREATED,
)
def submit_ticket_answer(
    ticket_id: UUID,
    payload: SubmitAnswerRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> KnowledgeCandidateView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    ticket = _get_ticket_or_404(database, ticket_id)
    _require_ticket_access(
        system_id=ticket.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    review_service = _build_review_service(request, database)
    candidate = review_service.submit_answer(
        ticket_id=ticket_id,
        author_id=context.account.id,
        answer=payload.answer,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.submit_answer",
        object_id=candidate.id,
        system_id=ticket.system_id,
    )
    return KnowledgeCandidateView.from_candidate(candidate)


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=KnowledgeCandidateView,
    status_code=status.HTTP_200_OK,
)
async def approve_candidate(
    candidate_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> KnowledgeCandidateView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.ADMIN, AccountRole.SYSTEM_OWNER},
    )
    review_service = _build_review_service(request, database)
    candidate = review_service.get_candidate(candidate_id=candidate_id)
    if candidate is None:
        raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
    _require_ticket_access(
        system_id=candidate.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    approved = await review_service.approve(
        candidate_id=candidate_id,
        reviewer_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.approve_candidate",
        object_id=candidate_id,
        system_id=candidate.system_id,
    )
    return KnowledgeCandidateView.from_candidate(approved)


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=KnowledgeCandidateView,
    status_code=status.HTTP_200_OK,
)
def reject_candidate(
    candidate_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> KnowledgeCandidateView:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.ADMIN, AccountRole.SYSTEM_OWNER},
    )
    review_service = _build_review_service(request, database)
    candidate = review_service.get_candidate(candidate_id=candidate_id)
    if candidate is None:
        raise NotFoundError("KNOWLEDGE_CANDIDATE_NOT_FOUND", "知识候选不存在")
    _require_ticket_access(
        system_id=candidate.system_id,
        account=context.account,
        database=database,
    )
    now = datetime.now(UTC)
    rejected = review_service.reject(
        candidate_id=candidate_id,
        reviewer_id=context.account.id,
        now=now,
    )
    _record_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="ticket.reject_candidate",
        object_id=candidate_id,
        system_id=candidate.system_id,
    )
    return KnowledgeCandidateView.from_candidate(rejected)


# Helpers


def _get_ticket_or_404(database: Session, ticket_id: UUID) -> Ticket:
    repository = SqlAlchemyTicketRepository(database)
    ticket = repository.get_ticket(ticket_id=ticket_id)
    if ticket is None:
        raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
    return ticket


def _require_ticket_access(
    *,
    system_id: UUID,
    account: Account,
    database: Session,
) -> None:
    # Thin wrapper around the shared access helper. Ticket read access for USER
    # mirrors the original behavior: an active system is reachable, while
    # management endpoints are already gated by auth.authorize() before this runs.
    _require_shared(
        system_id=system_id,
        account=account,
        database=database,
        allow_user=True,
    )


def _visible_system_ids(
    account: Account,
    database: Session,
) -> list[UUID]:
    return _visible_ids_shared(account, database)


def _record_audit(
    *,
    database: Session,
    request: Request,
    actor_id: UUID,
    action: str,
    object_id: UUID,
    system_id: UUID,
) -> None:
    SqlAlchemyAuditSink(database).record(
        action,
        "success",
        actor_id=actor_id,
        object_type="ticket",
        object_id=object_id,
        request_id=request.state.request_id,
        metadata={"system_id": str(system_id)},
    )


def _build_review_service(
    request: Request,
    database: Session,
) -> KnowledgeReviewService:
    settings = request.app.state.settings
    retrieval_settings = settings.retrieval
    embeddings = HttpEmbeddingProvider(
        base_url=retrieval_settings.embedding_base_url,
        model=retrieval_settings.embedding_model,
        timeout_seconds=retrieval_settings.embedding_timeout_seconds,
    )
    return KnowledgeReviewService(
        repository=SqlAlchemyTicketRepository(database),
        embeddings=embeddings,
    )
