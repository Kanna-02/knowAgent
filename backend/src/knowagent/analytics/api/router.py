from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from knowagent.analytics.api.schemas import (
    FrequentQuestionPage,
    FrequentQuestionView,
    KnowledgeGapPage,
    KnowledgeGapView,
    SystemOverviewView,
)
from knowagent.analytics.application.analytics_service import AnalyticsService
from knowagent.analytics.domain.models import AnalyticsWindow
from knowagent.common.errors import ValidationError
from knowagent.identity.api.access import require_system_access
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CurrentContextDependency,
    DatabaseSession,
)
from knowagent.identity.domain.models import AccountRole

router = APIRouter()

ANALYTICS_ROLES = {AccountRole.SYSTEM_OWNER, AccountRole.ADMIN}

DEFAULT_DAYS = 30
MAX_DAYS = 365
DEFAULT_TOP_N = 20
MAX_TOP_N = 100


def _parse_window(started_at: datetime | None, ended_at: datetime | None) -> AnalyticsWindow:
    now = datetime.now(UTC)
    end = ended_at if ended_at is not None else now
    start = started_at if started_at is not None else _default_start(end)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    try:
        return AnalyticsWindow(started_at=start, ended_at=end)
    except ValueError as error:
        raise ValidationError("ANALYTICS_WINDOW_INVALID", str(error)) from error


def _default_start(ended_at: datetime) -> datetime:
    return ended_at - timedelta(days=DEFAULT_DAYS)


@router.get(
    "/systems/{system_id}/analytics/overview",
    response_model=SystemOverviewView,
)
def get_system_overview(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    started_at: Annotated[datetime | None, Query()] = None,
    ended_at: Annotated[datetime | None, Query()] = None,
) -> SystemOverviewView:
    auth.authorize(context.account, allowed_roles=ANALYTICS_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    window = _parse_window(started_at, ended_at)
    overview = AnalyticsService(database).get_system_overview(
        system_id=system_id,
        window=window,
    )
    return SystemOverviewView(
        system_id=overview.system_id,
        question_count=overview.question_count,
        refusal_count=overview.refusal_count,
        open_ticket_count=overview.open_ticket_count,
        resolved_ticket_count=overview.resolved_ticket_count,
        total_ticket_count=overview.total_ticket_count,
    )


@router.get(
    "/systems/{system_id}/analytics/frequent-questions",
    response_model=FrequentQuestionPage,
)
def list_frequent_questions(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    started_at: Annotated[datetime | None, Query()] = None,
    ended_at: Annotated[datetime | None, Query()] = None,
    top_n: Annotated[int, Query(ge=1, le=MAX_TOP_N)] = DEFAULT_TOP_N,
) -> FrequentQuestionPage:
    auth.authorize(context.account, allowed_roles=ANALYTICS_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    window = _parse_window(started_at, ended_at)
    items = AnalyticsService(database).list_frequent_questions(
        system_id=system_id,
        window=window,
        top_n=top_n,
    )
    return FrequentQuestionPage(
        items=[
            FrequentQuestionView(
                normalized_question=item.normalized_question,
                occurrence_count=item.occurrence_count,
                refusal_count=item.refusal_count,
                ticket_count=item.ticket_count,
            )
            for item in items
        ],
        total=len(items),
    )


@router.get(
    "/systems/{system_id}/analytics/knowledge-gaps",
    response_model=KnowledgeGapPage,
)
def list_knowledge_gaps(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    system_id: UUID,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    started_at: Annotated[datetime | None, Query()] = None,
    ended_at: Annotated[datetime | None, Query()] = None,
    top_n: Annotated[int, Query(ge=1, le=MAX_TOP_N)] = DEFAULT_TOP_N,
) -> KnowledgeGapPage:
    auth.authorize(context.account, allowed_roles=ANALYTICS_ROLES)
    require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    window = _parse_window(started_at, ended_at)
    items = AnalyticsService(database).list_knowledge_gaps(
        system_id=system_id,
        window=window,
        top_n=top_n,
    )
    return KnowledgeGapPage(
        items=[
            KnowledgeGapView(
                normalized_question=gap.normalized_question,
                gap_source=gap.gap_source,
                occurrence_count=gap.occurrence_count,
                last_seen_at=gap.last_seen_at,
            )
            for gap in items
        ],
        total=len(items),
    )
