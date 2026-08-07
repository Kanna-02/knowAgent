from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from knowagent.agent.domain.models import PromptDefinition
from knowagent.agent.infrastructure.prompt_repository import PromptRepository
from knowagent.common.errors import ConflictError, NotFoundError
from knowagent.identity.infrastructure.sqlalchemy_models import Base

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
SCENARIO = "grounded_answer"
VERSION_V1 = "grounded-answer-v1"
VERSION_V2 = "grounded-answer-v2"


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _definition(
    scenario: str = SCENARIO,
    version: str = VERSION_V2,
    enabled: bool = False,
    change_note: str = "v2 with stricter citation rules",
) -> PromptDefinition:
    return PromptDefinition(
        scenario=scenario,
        version=version,
        content="你是企业知识问答助手。",
        enabled=enabled,
        created_at=NOW,
        change_note=change_note,
    )


def test_get_active_returns_db_row_when_enabled() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition(version=VERSION_V2, enabled=False))
        repo.save(_definition(version=VERSION_V1, enabled=True))
        active = repo.get_active(SCENARIO)
        assert active.version == VERSION_V1
        assert active.scenario == SCENARIO
        assert active.enabled is True


def test_get_active_returns_none_when_no_db_rows() -> None:
    """get_active cannot map a scenario back to a packaged version.

    The packaged registry keys by version, so get_active returns None until a
    DB row is seeded.
    """
    with _create_session() as session:
        repo = PromptRepository(session)
        assert repo.get_active(SCENARIO) is None


def test_get_version_returns_specific_version_regardless_of_enabled() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition(version=VERSION_V2, enabled=False))
        repo.save(_definition(version=VERSION_V1, enabled=True))
        v2 = repo.get_version(SCENARIO, VERSION_V2)
        assert v2.version == VERSION_V2
        assert v2.enabled is False
        v1 = repo.get_version(SCENARIO, VERSION_V1)
        assert v1.version == VERSION_V1
        assert v1.enabled is True


def test_get_version_for_unknown_db_row_falls_back_to_packaged() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        v1 = repo.get_version(SCENARIO, VERSION_V1)
        assert v1.version == VERSION_V1
        assert v1.enabled is True


def test_save_persists_new_definition_and_preserves_timezone() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        saved = repo.save(_definition())
        assert saved.version == VERSION_V2
        assert saved.created_at.tzinfo is not None
        reloaded = repo.get_version(SCENARIO, VERSION_V2)
        assert reloaded.version == VERSION_V2
        assert reloaded.content == "你是企业知识问答助手。"


def test_save_duplicate_scenario_version_raises() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition())
        with pytest.raises(ConflictError):
            repo.save(_definition())


def test_activate_switches_enabled_flag_for_scenario() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition(version=VERSION_V1, enabled=True))
        repo.save(_definition(version=VERSION_V2, enabled=False))
        activated = repo.activate(SCENARIO, VERSION_V2)
        assert activated.version == VERSION_V2
        assert activated.enabled is True
        v1 = repo.get_version(SCENARIO, VERSION_V1)
        assert v1.enabled is False
        v2 = repo.get_version(SCENARIO, VERSION_V2)
        assert v2.enabled is True


def test_activate_unknown_version_keeps_current_active() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition(version=VERSION_V1, enabled=True))
        with pytest.raises(NotFoundError):
            repo.activate(SCENARIO, "missing")
        assert repo.get_active(SCENARIO).version == VERSION_V1


def test_list_page_filters_scenario_and_reports_total() -> None:
    with _create_session() as session:
        repo = PromptRepository(session)
        repo.save(_definition(version=VERSION_V1, enabled=True))
        repo.save(_definition(scenario="query_rewrite", version="query-rewrite-v2"))
        items, total = repo.list_page(scenario=SCENARIO, page=1, page_size=10)
        assert total == 1
        assert [item.version for item in items] == [VERSION_V1]
