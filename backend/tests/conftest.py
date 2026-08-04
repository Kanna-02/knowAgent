from __future__ import annotations

import pytest

# Importing all ORM model modules ensures that every table derived from
# ``Base.metadata`` is registered before any test calls ``create_all()``.
# Without this, a test that only imports the ticket module would miss the
# knowledge tables referenced by ``knowledge_candidates`` and fail with a
# ``NoReferencedTableError``.
from knowagent.agent.infrastructure import sqlalchemy_models as _agent_models  # noqa: F401
from knowagent.documents.infrastructure import sqlalchemy_models as _document_models  # noqa: F401
from knowagent.identity.infrastructure.sqlalchemy_models import Base  # noqa: F401
from knowagent.knowledge.infrastructure import sqlalchemy_models as _knowledge_models  # noqa: F401
from knowagent.systems.infrastructure import sqlalchemy_models as _systems_models  # noqa: F401
from knowagent.tickets.infrastructure import sqlalchemy_models as _ticket_models  # noqa: F401


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
