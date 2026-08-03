from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from knowagent.common.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from knowagent.tickets.domain.models import (
    ReplyAuthorRole,
    Ticket,
    TicketReply,
    TicketStatus,
    TicketTransition,
    allowed_transitions,
)
from knowagent.tickets.ports import TicketRepository

REPLY_BODY_MAX_LENGTH = 10_000
ASSIGN_ACTION = "assign"
START_ACTION = "start"
REPLY_ACTION = "reply"
CLOSE_ACTION = "close"
REOPEN_ACTION = "reopen"
RESOLVE_ACTION = "resolve"


class TicketWorkflowService:
    """Drives ticket state transitions and append-only replies.

    Every public method serializes on the ticket row lock, validates the
    requested status change against :func:`allowed_transitions`, persists the
    outcome as an immutable :class:`TicketTransition`, and records replies
    when the caller supplies a body. Callers are expected to already be
    authenticated; this service only enforces ownership/role rules derivable
    from the ticket itself.
    """

    def __init__(self, *, repository: TicketRepository) -> None:
        self._repository = repository

    def assign(
        self,
        *,
        ticket_id: UUID,
        assignee_id: UUID,
        actor_id: UUID,
        now: datetime,
    ) -> Ticket:
        if now.tzinfo is None:
            raise ValueError("assign time must be timezone-aware")
        ticket = self._lock_existing(ticket_id)
        self._assert_transition(ticket.status, TicketStatus.ASSIGNED)
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=TicketStatus.ASSIGNED,
            assignee_id=assignee_id,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=actor_id,
            to_status=TicketStatus.ASSIGNED,
            action=ASSIGN_ACTION,
            now=now,
        )
        return self._refresh_ticket(ticket.id)

    def start(
        self,
        *,
        ticket_id: UUID,
        actor_id: UUID,
        now: datetime,
    ) -> Ticket:
        if now.tzinfo is None:
            raise ValueError("start time must be timezone-aware")
        ticket = self._lock_existing(ticket_id)
        self._assert_transition(ticket.status, TicketStatus.IN_PROGRESS)
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=TicketStatus.IN_PROGRESS,
            assignee_id=None,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=actor_id,
            to_status=TicketStatus.IN_PROGRESS,
            action=START_ACTION,
            now=now,
        )
        return self._refresh_ticket(ticket.id)

    def reply(
        self,
        *,
        ticket_id: UUID,
        author_id: UUID,
        body: str,
        now: datetime,
        transition_to: TicketStatus | None = None,
        action: str | None = None,
   ) -> tuple[TicketReply, Ticket]:
        # pylint: disable=too-many-arguments
        if now.tzinfo is None:
            raise ValueError("reply time must be timezone-aware")
        trimmed = body.strip()
        if not trimmed:
            raise ValidationError("TICKET_REPLY_BLANK", "工单回复内容不能为空")
        if len(trimmed) > REPLY_BODY_MAX_LENGTH:
            raise ValidationError("TICKET_REPLY_TOO_LONG", "工单回复内容超出最大长度")
        ticket = self._lock_existing(ticket_id)
        role = self._infer_role(ticket=ticket, author_id=author_id)
        reply = self._repository.add_reply(
            TicketReply(
                id=uuid4(),
                ticket_id=ticket_id,
                system_id=ticket.system_id,
                author_id=author_id,
                author_role=role,
                body=trimmed,
                created_at=now,
            )
        )
        if transition_to is None:
            return reply, ticket
        self._assert_transition(ticket.status, transition_to)
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=transition_to,
            assignee_id=None,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=author_id,
            to_status=transition_to,
            action=action or REPLY_ACTION,
            now=now,
        )
        return reply, self._refresh_ticket(ticket.id)

    def close(
        self,
        *,
        ticket_id: UUID,
        actor_id: UUID,
        now: datetime,
        body: str | None = None,
    ) -> Ticket:
        if now.tzinfo is None:
            raise ValueError("close time must be timezone-aware")
        ticket = self._lock_existing(ticket_id)
        self._assert_transition(ticket.status, TicketStatus.CLOSED)
        if body is not None and body.strip():
            self.reply(
                ticket_id=ticket_id,
                author_id=actor_id,
                body=body,
                now=now,
            )
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=TicketStatus.CLOSED,
            assignee_id=None,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=actor_id,
            to_status=TicketStatus.CLOSED,
            action=CLOSE_ACTION,
            now=now,
        )
        return self._refresh_ticket(ticket.id)

    def reopen(
        self,
        *,
        ticket_id: UUID,
        actor_id: UUID,
        now: datetime,
        body: str | None = None,
    ) -> Ticket:
        if now.tzinfo is None:
            raise ValueError("reopen time must be timezone-aware")
        ticket = self._lock_existing(ticket_id)
        self._assert_transition(ticket.status, TicketStatus.OPEN)
        if body is not None and body.strip():
            self.reply(
                ticket_id=ticket_id,
                author_id=actor_id,
                body=body,
                now=now,
            )
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=TicketStatus.OPEN,
            assignee_id=None,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=actor_id,
            to_status=TicketStatus.OPEN,
            action=REOPEN_ACTION,
            now=now,
        )
        return self._refresh_ticket(ticket.id)

    def resolve(
        self,
        *,
        ticket_id: UUID,
        actor_id: UUID,
        now: datetime,
    ) -> Ticket:
        """Transition a processing ticket to RESOLVED to hand it off to a reviewer."""
        if now.tzinfo is None:
            raise ValueError("resolve time must be timezone-aware")
        ticket = self._lock_existing(ticket_id)
        self._assert_transition(ticket.status, TicketStatus.RESOLVED)
        self._repository.update_ticket_status(
            ticket_id=ticket_id,
            status=TicketStatus.RESOLVED,
            assignee_id=None,
            now=now,
        )
        self._record_transition(
            ticket=ticket,
            actor_id=actor_id,
            to_status=TicketStatus.RESOLVED,
            action=RESOLVE_ACTION,
            now=now,
        )
        return self._refresh_ticket(ticket.id)

    def list_replies(self, *, ticket_id: UUID) -> tuple[TicketReply, ...]:
        return self._repository.list_replies(ticket_id=ticket_id)

    def list_transitions(self, *, ticket_id: UUID) -> tuple[TicketTransition, ...]:
        return self._repository.list_transitions(ticket_id=ticket_id)

    # ---- internal helpers ----

    def _lock_existing(self, ticket_id: UUID) -> Ticket:
        ticket = self._repository.lock_ticket(ticket_id=ticket_id)
        if ticket is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        return ticket

    @staticmethod
    def _assert_transition(
        current: TicketStatus,
        target: TicketStatus,
    ) -> None:
        if current is target:
            raise ConflictError("TICKET_SAME_STATUS", "工单状态未变化")
        if target not in allowed_transitions(current):
            raise ConflictError(
                "TICKET_INVALID_TRANSITION",
                f"不允许从 {current.value} 转换到 {target.value}",
            )

    @staticmethod
    def _infer_role(*, ticket: Ticket, author_id: UUID) -> ReplyAuthorRole:
        if author_id == ticket.requester_id:
            return ReplyAuthorRole.REQUESTER
        if ticket.assignee_id is not None and author_id == ticket.assignee_id:
            return ReplyAuthorRole.ASSIGNEE
        # Reviewers and other authorised participants fall back to REVIEWER; the
        # API layer is responsible for ensuring the actor has system access.
        return ReplyAuthorRole.REVIEWER

    def _record_transition(
        self,
        *,
        ticket: Ticket,
        actor_id: UUID,
        to_status: TicketStatus,
        action: str,
        now: datetime,
    ) -> TicketTransition:
        return self._repository.add_transition(
            TicketTransition(
                id=uuid4(),
                ticket_id=ticket.id,
                system_id=ticket.system_id,
                actor_id=actor_id,
                from_status=ticket.status,
                to_status=to_status,
                action=action,
                created_at=now,
            )
        )

    def _refresh_ticket(self, ticket_id: UUID) -> Ticket:
        refreshed = self._repository.lock_ticket(ticket_id=ticket_id)
        if refreshed is None:
            raise NotFoundError("TICKET_NOT_FOUND", "工单不存在")
        return refreshed
