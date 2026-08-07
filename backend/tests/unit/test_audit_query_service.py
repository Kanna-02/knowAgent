from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.audit.application.audit_query_service import (
    AuditLogFilter,
    AuditQueryService,
)
from knowagent.audit.domain.models import AuditLogEntry
from knowagent.identity.infrastructure.sqlalchemy_models import (
    AuditLogRecord,
    Base,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
ACTOR_ID = uuid4()


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_audit_record(
    session: Session,
    *,
    action: str = "test.action",
    result: str = "success",
    object_type: str | None = None,
    object_id: uuid4 | None = None,
    actor_id: uuid4 | None = None,
    created_at: datetime | None = None,
) -> None:
    session.add(
        AuditLogRecord(
            id=uuid4(),
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            result=result,
            request_id=None,
            context_data=None,
            created_at=created_at or NOW,
        )
    )
    session.flush()


class TestAuditQueryService:
    def test_list_audit_logs_empty(self) -> None:
        with _create_session() as session:
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(page=1, page_size=10)
            assert entries == []
            assert total == 0

    def test_list_audit_logs_returns_entries_ordered_desc(self) -> None:
        with _create_session() as session:
            _seed_audit_record(session, action="a.first", created_at=NOW - timedelta(days=2))
            _seed_audit_record(session, action="a.second", created_at=NOW - timedelta(days=1))
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(page=1, page_size=10)
            assert total == 2
            assert len(entries) == 2
            assert entries[0].action == "a.second"
            assert entries[1].action == "a.first"

    def test_list_audit_logs_filters_by_action(self) -> None:
        with _create_session() as session:
            _seed_audit_record(session, action="user.login")
            _seed_audit_record(session, action="ticket.assign")
            _seed_audit_record(session, action="user.login")
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(
                page=1,
                page_size=10,
                filters=AuditLogFilter(action="user.login"),
            )
            assert total == 2
            assert all(entry.action == "user.login" for entry in entries)

    def test_list_audit_logs_filters_by_result(self) -> None:
        with _create_session() as session:
            _seed_audit_record(session, result="success")
            _seed_audit_record(session, result="failure")
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(
                page=1,
                page_size=10,
                filters=AuditLogFilter(result="failure"),
            )
            assert total == 1
            assert entries[0].result == "failure"

    def test_list_audit_logs_filters_by_time_window(self) -> None:
        with _create_session() as session:
            _seed_audit_record(
                session,
                action="old",
                created_at=NOW - timedelta(days=30),
            )
            _seed_audit_record(
                session,
                action="recent",
                created_at=NOW - timedelta(days=1),
            )
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(
                page=1,
                page_size=10,
                filters=AuditLogFilter(
                    started_at=NOW - timedelta(days=7),
                    ended_at=NOW,
                ),
            )
            assert total == 1
            assert entries[0].action == "recent"

    def test_list_audit_logs_filters_by_actor(self) -> None:
        with _create_session() as session:
            actor = uuid4()
            _seed_audit_record(session, actor_id=actor, action="hit")
            _seed_audit_record(session, actor_id=uuid4(), action="miss")
            service = AuditQueryService(session)
            entries, total = service.list_audit_logs(
                page=1,
                page_size=10,
                filters=AuditLogFilter(actor_id=actor),
            )
            assert total == 1
            assert entries[0].action == "hit"

    def test_list_audit_logs_paginates(self) -> None:
        with _create_session() as session:
            for i in range(15):
                _seed_audit_record(
                    session,
                    action=f"a.{i:02d}",
                    created_at=NOW - timedelta(minutes=i),
                )
            service = AuditQueryService(session)
            page1, total1 = service.list_audit_logs(page=1, page_size=10)
            page2, total2 = service.list_audit_logs(page=2, page_size=10)
            assert total1 == 15 and total2 == 15
            assert len(page1) == 10 and len(page2) == 5
            # No overlap between pages.
            ids_page1 = {entry.id for entry in page1}
            ids_page2 = {entry.id for entry in page2}
            assert ids_page1.isdisjoint(ids_page2)
            assert {entry.id for entry in page1} != set()

    def test_list_audit_logs_rejects_non_positive_pagination(self) -> None:
        with _create_session() as session:
            service = AuditQueryService(session)
            with pytest.raises(ValueError, match="positive"):
                service.list_audit_logs(page=0, page_size=10)
            with pytest.raises(ValueError, match="positive"):
                service.list_audit_logs(page=1, page_size=0)

    def test_audit_log_entry_rejects_blank_action(self) -> None:
        with pytest.raises(ValueError, match="must not be blank"):
            AuditLogEntry(
                id=uuid4(),
                actor_id=None,
                action="",
                object_type=None,
                object_id=None,
                result="success",
                request_id=None,
                context_data=None,
                created_at=NOW,
                detail=None,
            )

    def test_audit_log_entry_rejects_naive_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AuditLogEntry(
                id=uuid4(),
                actor_id=None,
                action="test",
                object_type=None,
                object_id=None,
                result="success",
                request_id=None,
                context_data=None,
                created_at=datetime(2026, 8, 7, 12, 0),
                detail=None,
            )
