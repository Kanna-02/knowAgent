from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from knowagent.agent.api.admin_schemas import (
    ConversationDetail,
    ConversationMessageView,
    ConversationPage,
    ConversationView,
    CreateConversationRequest,
)
from knowagent.agent.application.conversation_service import ConversationService
from knowagent.agent.domain.conversation import Conversation
from knowagent.common.errors import NotFoundError
from knowagent.identity.api.access import require_system_access
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
)
from knowagent.identity.domain.models import AccountRole
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink

router = APIRouter()

# Full conversation detail returned to the client. Intentionally larger
# than REWRITE_CONTEXT_HISTORY_LIMIT in conversation_service: the detail
# endpoint needs to show more context, query-rewrite only needs recent turns.
CONVERSATION_HISTORY_LIMIT = 50
ALLOWED_ROLES = {AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN}


@router.post(
    "/conversations",
    response_model=ConversationView,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: CreateConversationRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> ConversationView:
    auth.authorize(context.account, allowed_roles=ALLOWED_ROLES)
    require_system_access(
        system_id=payload.system_id,
        account=context.account,
        database=database,
        allow_user=True,
    )
    conversation = ConversationService(database).create_conversation(
        system_id=payload.system_id,
        account_id=context.account.id,
        title=payload.title,
        now=datetime.now(UTC),
    )
    SqlAlchemyAuditSink(database).record(
        "conversation.create",
        "success",
        actor_id=context.account.id,
        object_type="conversation",
        object_id=conversation.id,
        request_id=request.state.request_id,
        metadata={"system_id": str(conversation.system_id)},
    )
    return _to_view(conversation)


@router.get("/conversations", response_model=ConversationPage)
def list_conversations(
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    system_id: Annotated[UUID, Query()],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationPage:
    auth.authorize(context.account, allowed_roles=ALLOWED_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
        allow_user=True,
    )
    items, total = ConversationService(database).list_conversations(
        system_id=system_id,
        account_id=context.account.id,
        page=page,
        page_size=page_size,
    )
    return ConversationPage(
        items=[_to_view(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> ConversationDetail:
    auth.authorize(context.account, allowed_roles=ALLOWED_ROLES)
    service = ConversationService(database)
    conversation = _get_owned_conversation(
        service=service,
        conversation_id=conversation_id,
        account_id=context.account.id,
    )
    require_system_access(
        system_id=conversation.system_id,
        account=context.account,
        database=database,
        allow_user=True,
    )
    messages = service.list_messages(
        conversation_id=conversation.id,
        system_id=conversation.system_id,
        limit=CONVERSATION_HISTORY_LIMIT,
    )
    return ConversationDetail(
        conversation=_to_view(conversation),
        messages=[
            ConversationMessageView(
                id=message.id,
                role=message.role.value,
                content=message.content,
                intent=message.intent.value if message.intent is not None else None,
                rewritten_query=message.rewritten_query,
                rewrite_prompt_version=message.rewrite_prompt_version,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> None:
    auth.authorize(context.account, allowed_roles=ALLOWED_ROLES)
    service = ConversationService(database)
    conversation = _get_owned_conversation(
        service=service,
        conversation_id=conversation_id,
        account_id=context.account.id,
    )
    require_system_access(
        system_id=conversation.system_id,
        account=context.account,
        database=database,
        allow_user=True,
    )
    service.delete_conversation(
        conversation_id=conversation.id,
        system_id=conversation.system_id,
    )
    SqlAlchemyAuditSink(database).record(
        "conversation.delete",
        "success",
        actor_id=context.account.id,
        object_type="conversation",
        object_id=conversation.id,
        request_id=request.state.request_id,
        metadata={"system_id": str(conversation.system_id)},
    )


def _get_owned_conversation(
    *,
    service: ConversationService,
    conversation_id: UUID,
    account_id: UUID,
) -> Conversation:
    conversation = service.get_conversation_by_id(conversation_id)
    if conversation.account_id != account_id:
        raise NotFoundError("CONVERSATION_NOT_FOUND", "会话不存在或无权访问")
    return conversation


def _to_view(conversation: Conversation) -> ConversationView:
    return ConversationView(
        id=conversation.id,
        system_id=conversation.system_id,
        account_id=conversation.account_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )
