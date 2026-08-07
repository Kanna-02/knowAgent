from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.application.conversation_service import ConversationService
from knowagent.agent.domain.conversation import (
    ConversationMessage,
    ConversationMessageRole,
    IntentKind,
)
from knowagent.common.errors import NotFoundError, ValidationError
from knowagent.identity.infrastructure.sqlalchemy_models import Base

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
ACCOUNT_ID = uuid4()
SYSTEM_ID = uuid4()


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_system_and_account(session: Session) -> None:
    from knowagent.identity.domain.models import AccountRole, AccountSource, AccountStatus
    from knowagent.identity.infrastructure.sqlalchemy_models import AccountRecord
    from knowagent.systems.domain.models import BusinessSystemStatus
    from knowagent.systems.infrastructure.sqlalchemy_models import BusinessSystemRecord

    session.add(
        AccountRecord(
            id=ACCOUNT_ID,
            username="tester",
            display_name="Test User",
            password_hash="dummy",
            role=AccountRole.USER,
            source=AccountSource.ADMIN_CREATED,
            status=AccountStatus.ACTIVE,
            must_change_password=False,
            session_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        BusinessSystemRecord(
            id=SYSTEM_ID,
            code="TEST_SYS",
            name="Test System",
            description="test",
            status=BusinessSystemStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.flush()


def test_create_conversation_appends_and_lists_messages() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="部署排错",
            now=NOW,
        )
        user_msg = service.append_message(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            role=ConversationMessageRole.USER,
            content="如何执行数据库迁移？",
            intent=IntentKind.STANDALONE,
            rewritten_query="如何执行数据库迁移？",
            now=NOW,
        )
        assistant_msg = service.append_message(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            role=ConversationMessageRole.ASSISTANT,
            content="先运行 alembic upgrade head。",
            now=NOW,
        )
        history = service.list_messages(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
        )
        assert len(history) == 2
        assert history[0].role is ConversationMessageRole.USER
        assert history[0].content == "如何执行数据库迁移？"
        assert history[0].intent is IntentKind.STANDALONE
        assert history[0].rewritten_query == "如何执行数据库迁移？"
        assert history[1].role is ConversationMessageRole.ASSISTANT
        assert user_msg.id != assistant_msg.id
        assert isinstance(user_msg, ConversationMessage)


def test_list_recent_questions_returns_only_user_turns() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="多轮排错",
            now=NOW,
        )
        service.append_message(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            role=ConversationMessageRole.USER,
            content="什么是 ESB？",
            now=NOW,
        )
        service.append_message(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            role=ConversationMessageRole.ASSISTANT,
            content="ESB 是企业服务总线。",
            now=NOW,
        )
        service.append_message(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            role=ConversationMessageRole.USER,
            content="它的版本管理怎么用？",
            now=NOW,
        )
        history = service.list_recent_questions(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
        )
        assert len(history) == 2
        assert history[0] == "什么是 ESB？"
        assert history[1] == "它的版本管理怎么用？"


def test_cross_system_access_raises_not_found() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="隔离测试",
            now=NOW,
        )
        other_system = uuid4()
        with pytest.raises(NotFoundError):
            service.get_conversation(
                conversation_id=conversation.id,
                system_id=other_system,
            )


def test_cross_account_access_raises_not_found() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="账号隔离测试",
            now=NOW,
        )
        with pytest.raises(NotFoundError):
            service.get_conversation(
                conversation_id=conversation.id,
                system_id=SYSTEM_ID,
                account_id=uuid4(),
            )


def test_blank_title_raises_validation_error() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        with pytest.raises(ValidationError):
            service.create_conversation(
                system_id=SYSTEM_ID,
                account_id=ACCOUNT_ID,
                title="   ",
                now=NOW,
            )


def test_blank_message_content_raises_validation_error() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="空消息测试",
            now=NOW,
        )
        with pytest.raises(ValidationError):
            service.append_message(
                conversation_id=conversation.id,
                system_id=SYSTEM_ID,
                role=ConversationMessageRole.USER,
                content="",
                now=NOW,
            )


def test_sequence_numbers_are_monotonic() -> None:
    with _create_session() as session:
        _seed_system_and_account(session)
        service = ConversationService(session)
        conversation = service.create_conversation(
            system_id=SYSTEM_ID,
            account_id=ACCOUNT_ID,
            title="序列号测试",
            now=NOW,
        )
        for i in range(3):
            service.append_message(
                conversation_id=conversation.id,
                system_id=SYSTEM_ID,
                role=ConversationMessageRole.USER,
                content=f"问题 {i}",
                now=NOW,
            )
        history = service.list_messages(
            conversation_id=conversation.id,
            system_id=SYSTEM_ID,
            limit=10,
        )
        assert len(history) == 3
        contents = [msg.content for msg in history]
        assert contents == ["问题 0", "问题 1", "问题 2"]
