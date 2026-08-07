from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowagent.agent.domain.conversation import (
    Conversation,
    ConversationMessage,
    ConversationMessageRole,
    IntentKind,
)
from knowagent.agent.infrastructure.sqlalchemy_models import (
    ConversationMessageRecord,
    ConversationRecord,
)
from knowagent.common.errors import NotFoundError, ValidationError


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# Default limit for query-rewrite context: only recent turns matter for
# anaphoric resolution, so 10 is enough. CONVERSATION_HISTORY_LIMIT in
# conversations_router is larger (50) because that endpoint returns the
# full conversation detail to the client. The two limits are intentionally
# different -- rewrite context is cheap and bounded, full history is richer.
REWRITE_CONTEXT_HISTORY_LIMIT = 10


class ConversationService:  # pylint: disable=too-few-public-methods
    """Creates conversations and appends/reads messages in a system scope.

    All access is scoped by ``system_id`` so the caller cannot cross business
    system boundaries. History reads are capped by ``history_limit`` (default
    ``REWRITE_CONTEXT_HISTORY_LIMIT``) to bound prompt cost on long conversations.
    """

    def __init__(
        self, session: Session, *, history_limit: int = REWRITE_CONTEXT_HISTORY_LIMIT
    ) -> None:
        if history_limit <= 0:
            raise ValueError("conversation history limit must be positive")
        self._session = session
        self._history_limit = history_limit

    def create_conversation(
        self,
        *,
        system_id: UUID,
        account_id: UUID,
        title: str,
        now: datetime,
    ) -> Conversation:
        if not title.strip():
            raise ValidationError(
                "CONVERSATION_TITLE_BLANK",
                "会话标题不能为空",
            )
        record = ConversationRecord(
            id=uuid4(),
            system_id=system_id,
            account_id=account_id,
            title=title.strip(),
            created_at=now,
            updated_at=now,
        )
        with self._session.begin_nested():
            self._session.add(record)
            self._session.flush()
        return self._to_domain(record)

    def get_conversation(
        self,
        *,
        conversation_id: UUID,
        system_id: UUID,
        account_id: UUID | None = None,
    ) -> Conversation:
        conditions = [
            ConversationRecord.id == conversation_id,
            ConversationRecord.system_id == system_id,
        ]
        if account_id is not None:
            conditions.append(ConversationRecord.account_id == account_id)
        record = self._session.scalar(select(ConversationRecord).where(*conditions))
        if record is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND", "会话不存在或无权访问")
        return self._to_domain(record)

    def get_conversation_by_id(
        self,
        conversation_id: UUID,
    ) -> Conversation:
        """Return a conversation regardless of system scope.

        Access control is the caller's responsibility: use this only after
        enforcing system ownership and per-account visibility.
        """
        record = self._session.get(ConversationRecord, conversation_id)
        if record is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND", "会话不存在或无权访问")
        return self._to_domain(record)

    def delete_conversation(
        self,
        *,
        conversation_id: UUID,
        system_id: UUID,
    ) -> None:
        """Remove a conversation, its messages cascading on-delete."""
        record = self._session.get(ConversationRecord, conversation_id)
        if record is None or record.system_id != system_id:
            raise NotFoundError("CONVERSATION_NOT_FOUND", "会话不存在或无权访问")
        with self._session.begin_nested():
            self._session.delete(record)
            self._session.flush()

    def append_message(  # pylint: disable=too-many-arguments
        self,
        *,
        conversation_id: UUID,
        system_id: UUID,
        role: ConversationMessageRole,
        content: str,
        intent: IntentKind | None = None,
        rewritten_query: str | None = None,
        rewrite_prompt_version: str | None = None,
        now: datetime,
    ) -> ConversationMessage:
        if not content.strip():
            raise ValidationError(
                "CONVERSATION_MESSAGE_BLANK",
                "会话消息内容不能为空",
            )
        # Serialize sequence allocation for concurrent turns in one conversation.
        conversation_record = self._session.scalar(
            select(ConversationRecord)
            .where(
                ConversationRecord.id == conversation_id,
                ConversationRecord.system_id == system_id,
            )
            .with_for_update()
        )
        if conversation_record is None:
            raise NotFoundError("CONVERSATION_NOT_FOUND", "会话不存在或无权访问")
        max_sequence = self._session.scalar(
            select(func.max(ConversationMessageRecord.sequence_number)).where(
                ConversationMessageRecord.conversation_id == conversation_id,
                ConversationMessageRecord.system_id == system_id,
            )
        )
        sequence_number = (max_sequence or 0) + 1
        record = ConversationMessageRecord(
            id=uuid4(),
            conversation_id=conversation_id,
            system_id=system_id,
            sequence_number=sequence_number,
            role=role.value,
            content=content,
            intent=intent.value if intent is not None else None,
            rewritten_query=rewritten_query,
            rewrite_prompt_version=rewrite_prompt_version,
            created_at=now,
        )
        with self._session.begin_nested():
            self._session.add(record)
            # Bump conversation updated_at on new message.
            conversation_record.updated_at = now
            self._session.flush()
        return self._to_message_domain(record)

    def list_messages(
        self,
        *,
        conversation_id: UUID,
        system_id: UUID,
        limit: int | None = None,
    ) -> tuple[ConversationMessage, ...]:
        effective_limit = limit if limit is not None else self._history_limit
        if effective_limit <= 0:
            raise ValueError("conversation message limit must be positive")
        records = self._session.scalars(
            select(ConversationMessageRecord)
            .where(
                ConversationMessageRecord.conversation_id == conversation_id,
                ConversationMessageRecord.system_id == system_id,
            )
            .order_by(ConversationMessageRecord.sequence_number.desc())
            .limit(effective_limit)
        ).all()
        ordered = list(reversed(records))
        return tuple(self._to_message_domain(record) for record in ordered)

    def list_conversations(
        self,
        *,
        system_id: UUID,
        account_id: UUID | None = None,
        page: int,
        page_size: int,
    ) -> tuple[tuple[Conversation, ...], int]:
        """Return a page of conversations in a system scope.

        ``account_id`` restricts to the caller's own conversations (used for
        USER visibility). Pass ``None`` to list every conversation in the
        system (used by ADMIN or SYSTEM_OWNER managers). Results are ordered
        by most-recently-updated first.
        """
        if page <= 0 or page_size <= 0:
            raise ValueError("conversation pagination parameters must be positive")
        conditions = [ConversationRecord.system_id == system_id]
        if account_id is not None:
            conditions.append(ConversationRecord.account_id == account_id)
        total = self._session.scalar(
            select(func.count()).select_from(ConversationRecord).where(*conditions)
        )
        records = self._session.scalars(
            select(ConversationRecord)
            .where(*conditions)
            .order_by(ConversationRecord.updated_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        ).all()
        return tuple(self._to_domain(record) for record in records), int(total or 0)

    def list_recent_questions(
        self,
        *,
        conversation_id: UUID,
        system_id: UUID,
        limit: int = 5,
    ) -> tuple[str, ...]:
        """Return recent user questions for query rewriting context."""
        if limit <= 0:
            raise ValueError("recent question limit must be positive")
        records = self._session.scalars(
            select(ConversationMessageRecord)
            .where(
                ConversationMessageRecord.conversation_id == conversation_id,
                ConversationMessageRecord.system_id == system_id,
                ConversationMessageRecord.role == ConversationMessageRole.USER.value,
            )
            .order_by(ConversationMessageRecord.sequence_number.desc())
            .limit(limit)
        ).all()
        return tuple(record.content for record in reversed(records))

    @staticmethod
    def _to_domain(record: ConversationRecord) -> Conversation:
        return Conversation(
            id=record.id,
            system_id=record.system_id,
            account_id=record.account_id,
            title=record.title,
            created_at=_aware(record.created_at),
            updated_at=_aware(record.updated_at),
        )

    @staticmethod
    def _to_message_domain(record: ConversationMessageRecord) -> ConversationMessage:
        return ConversationMessage(
            id=record.id,
            conversation_id=record.conversation_id,
            role=ConversationMessageRole(record.role),
            content=record.content,
            intent=IntentKind(record.intent) if record.intent is not None else None,
            rewritten_query=record.rewritten_query,
            rewrite_prompt_version=record.rewrite_prompt_version,
            created_at=_aware(record.created_at),
        )
