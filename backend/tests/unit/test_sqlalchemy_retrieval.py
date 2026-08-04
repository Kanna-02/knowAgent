from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from knowagent.common.errors import ProviderUnavailableError
from knowagent.retrieval.infrastructure.sqlalchemy_search import PostgresKnowledgeSearch


def compiled_statement(session: MagicMock) -> str:
    statement = session.execute.call_args.args[0]
    return str(statement.compile(dialect=postgresql.dialect()))


def test_keyword_search_filters_system_and_publication_before_ranking() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.all.return_value = []
    repository = PostgresKnowledgeSearch(session)

    assert repository.search(system_id=uuid4(), query="部署", limit=8) == ()

    sql = compiled_statement(session)
    assert "knowledge_chunks.system_id =" in sql
    assert "knowledge_chunks.publish_status =" in sql
    assert "knowledge_sources.publish_status =" in sql
    assert "LEFT OUTER JOIN tickets" in sql
    assert "knowledge_sources.source_type =" not in sql.split("WHERE", maxsplit=1)[1]
    assert "similarity(knowledge_chunks.retrieval_text" in sql
    assert "LIMIT" in sql


def test_vector_search_filters_system_publication_and_model_contract() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.all.return_value = []
    repository = PostgresKnowledgeSearch(session)

    assert (
        repository.search_vectors(
            system_id=uuid4(),
            vector=(0.1, 0.2, 0.3),
            model="bge-m3",
            model_version="2026-08",
            limit=8,
        )
        == ()
    )

    sql = compiled_statement(session)
    assert "knowledge_chunks.system_id =" in sql
    assert "knowledge_chunks.publish_status =" in sql
    assert "knowledge_chunks.embedding_model =" in sql
    assert "knowledge_chunks.embedding_model_version =" in sql
    assert "knowledge_chunks.embedding IS NOT NULL" in sql
    assert "knowledge_sources.publish_status =" in sql
    assert "LEFT OUTER JOIN tickets" in sql
    assert "knowledge_sources.source_type =" not in sql.split("WHERE", maxsplit=1)[1]
    assert "<=>" in sql


def test_search_rejects_invalid_limits_queries_and_vectors_before_database_access() -> None:
    session = MagicMock(spec=Session)
    repository = PostgresKnowledgeSearch(session)

    with pytest.raises(ValueError, match="limit"):
        repository.search(system_id=uuid4(), query="部署", limit=0)
    with pytest.raises(ValueError, match="query"):
        repository.search(system_id=uuid4(), query="  ", limit=8)
    with pytest.raises(ValueError, match="vector"):
        repository.search_vectors(
            system_id=uuid4(),
            vector=(),
            model="bge-m3",
            model_version="2026-08",
            limit=8,
        )

    session.execute.assert_not_called()


def test_vector_search_maps_database_failure_and_rolls_back_failed_transaction() -> None:
    session = MagicMock(spec=Session)
    session.execute.side_effect = OperationalError(
        "SELECT embedding <=> query",
        {},
        RuntimeError("vector operator unavailable"),
    )
    repository = PostgresKnowledgeSearch(session)

    with pytest.raises(ProviderUnavailableError):
        repository.search_vectors(
            system_id=uuid4(),
            vector=(0.1, 0.2, 0.3),
            model="bge-m3",
            model_version="2026-08",
            limit=8,
        )

    session.rollback.assert_called_once_with()
