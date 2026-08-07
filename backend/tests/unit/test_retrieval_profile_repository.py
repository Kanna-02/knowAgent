from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.domain.conversation import RetrievalProfile
from knowagent.agent.infrastructure.retrieval_profile_repository import (
    RetrievalProfileRepository,
)
from knowagent.common.errors import ConflictError, NotFoundError
from knowagent.identity.infrastructure.sqlalchemy_models import Base

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
NAME = "default"
VERSION_V1 = "profile-v1"
VERSION_V2 = "profile-v2"


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _profile(
    name: str = NAME,
    version: str = VERSION_V2,
    is_active: bool = False,
    change_note: str = "tune rerank depth",
) -> RetrievalProfile:
    return RetrievalProfile(
        name=name,
        version=version,
        keyword_top_k=20,
        vector_top_k=20,
        result_top_k=10,
        rrf_k=60,
        keyword_weight=1.0,
        vector_weight=1.0,
        rerank_candidate_top_k=15,
        rerank_top_k=10,
        evidence_max_items=4,
        evidence_max_characters=600,
        is_active=is_active,
        created_at=NOW,
        change_note=change_note,
    )


def test_get_active_returns_none_when_no_rows() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        assert repo.get_active(NAME) is None


def test_save_and_get_active_returns_active_profile() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        repo.save(_profile(version=VERSION_V2, is_active=False))
        active = repo.get_active(NAME)
        assert active is not None
        assert active.version == VERSION_V1
        assert active.is_active is True
        assert active.keyword_top_k == 20


def test_get_version_returns_specific_version_regardless_of_active() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        repo.save(_profile(version=VERSION_V2, is_active=False))
        v2 = repo.get_version(NAME, VERSION_V2)
        assert v2 is not None
        assert v2.version == VERSION_V2
        assert v2.is_active is False


def test_get_version_returns_none_for_unknown_version() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        assert repo.get_version(NAME, VERSION_V2) is None


def test_save_duplicate_name_version_raises() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        with pytest.raises(ConflictError):
            repo.save(_profile(version=VERSION_V1, is_active=True))


def test_activate_switches_active_flag_for_name() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        repo.save(_profile(version=VERSION_V2, is_active=False))
        activated = repo.activate(NAME, VERSION_V2)
        assert activated.version == VERSION_V2
        assert activated.is_active is True
        v1 = repo.get_version(NAME, VERSION_V1)
        assert v1 is not None
        assert v1.is_active is False
        v2 = repo.get_version(NAME, VERSION_V2)
        assert v2 is not None
        assert v2.is_active is True


def test_activate_unknown_version_keeps_current_active() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        with pytest.raises(NotFoundError):
            repo.activate(NAME, "missing")
        active = repo.get_active(NAME)
        assert active is not None
        assert active.version == VERSION_V1


def test_list_page_filters_name_and_reports_total() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        repo.save(_profile(version=VERSION_V1, is_active=True))
        repo.save(_profile(name="experimental", version=VERSION_V2, is_active=False))
        items, total = repo.list_page(name=NAME, page=1, page_size=10)
        assert total == 1
        assert [item.version for item in items] == [VERSION_V1]


def test_save_preserves_timezone_on_reload() -> None:
    with _create_session() as session:
        repo = RetrievalProfileRepository(session)
        saved = repo.save(_profile(version=VERSION_V1, is_active=True))
        assert saved.created_at.tzinfo is not None
        reloaded = repo.get_version(NAME, VERSION_V1)
        assert reloaded is not None
        assert reloaded.created_at.tzinfo is not None
        assert reloaded.change_note == "tune rerank depth"
