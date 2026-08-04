from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, status
from sqlalchemy.orm import Session

from knowagent.agent.api.schemas import QuestionRequest, QuestionResponse
from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.answer_snapshots import AnswerSnapshotService
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.infrastructure.openai_compatible import OpenAiCompatibleLlmProvider
from knowagent.agent.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAnswerSnapshotRepository,
)
from knowagent.agent.prompts import load_prompt_definition
from knowagent.common.errors import (
    KnowAgentError,
)
from knowagent.identity.api.access import require_system_access as _require_shared
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    DatabaseSession,
)
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.application.retrieval_service import BasicRetrievalService
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider
from knowagent.retrieval.infrastructure.sqlalchemy_search import PostgresKnowledgeSearch
from knowagent.tickets.application.refusal import RefusalTicketService
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

LOGGER = logging.getLogger(__name__)
router = APIRouter()


class _NoopMetrics:  # pylint: disable=too-few-public-methods
    def record_degradation(self, *, system_id: UUID, channel: str, reason: str) -> None:
        pass


@router.post(
    "/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
)
async def ask_question(
    payload: QuestionRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
) -> QuestionResponse:
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    _require_system_access(
        system_id=payload.system_id,
        account=context.account,
        database=database,
    )
    settings = request.app.state.settings
    if not settings.llm.configured:
        raise KnowAgentError(
            "LLM_NOT_CONFIGURED",
            "语言模型尚未配置",
            status_code=503,
            details={"feature": "question_answering"},
        )
    run_id = uuid4()
    question_service = _build_question_service(request, database)
    resolution = await question_service.resolve(
        run_id=run_id,
        requester_id=context.account.id,
        system_id=payload.system_id,
        question=payload.question,
        required_terms=payload.required_terms_tuple,
    )
    return QuestionResponse.from_resolution(resolution)


def _require_system_access(
    *,
    system_id: UUID,
    account: Account,
    database: Session,
) -> None:
    # USER callers may ask questions against active systems; management
    # endpoints are gated separately. allow_user matches the original behavior.
    _require_shared(
        system_id=system_id,
        account=account,
        database=database,
        allow_user=True,
    )


def _build_question_service(
    request: Request,
    database: Session,
) -> ReliableQuestionService:
    settings = request.app.state.settings
    retrieval_settings = settings.retrieval
    ticket_settings = settings.tickets

    components = _get_or_build_agent_components(request)
    embeddings = components.embeddings
    search = PostgresKnowledgeSearch(database)
    retrieval = BasicRetrievalService(
        embeddings=embeddings,
        lexical=search,
        vectors=search,
        keyword_top_k=retrieval_settings.keyword_top_k,
        vector_top_k=retrieval_settings.vector_top_k,
        result_top_k=retrieval_settings.result_top_k,
        rrf_k=retrieval_settings.rrf_k,
        metrics=_NoopMetrics(),
    )
    evidence = EvidenceOrganizer(
        max_items=retrieval_settings.evidence_max_items,
        max_characters=retrieval_settings.evidence_max_characters,
    )
    policy = components.policy
    answers = components.answers
    ticket_repository = SqlAlchemyTicketRepository(database)
    refusal = RefusalTicketService(
        repository=ticket_repository,
        deduplication_window=timedelta(hours=ticket_settings.deduplication_window_hours),
    )
    snapshots = AnswerSnapshotService(
        repository=SqlAlchemyAnswerSnapshotRepository(database),
    )
    return ReliableQuestionService(
        retrieval=retrieval,
        evidence=evidence,
        policy=policy,
        answers=answers,
        recorder=refusal,
        snapshots=snapshots,
        clock=lambda: datetime.now(UTC),
    )


class _AgentComponents:  # pylint: disable=too-few-public-methods
    """Process-wide, request-independent objects backing question answering.

    The LLM and Embedding providers hold HTTP connection pools that are
    expensive to build per request. ``EvidenceOrganizer``/``AnswerGenerator``
    and the prompt definition are also stateless. They are created once per app
    process and reused across requests, while the SQLAlchemy Session stays
    request-scoped.
    """

    __slots__ = ("embeddings", "policy", "answers")

    def __init__(
        self,
        *,
        embeddings: HttpEmbeddingProvider,
        policy: DeterministicEvidencePolicy,
        answers: AnswerGenerator,
    ) -> None:
        self.embeddings = embeddings
        self.policy = policy
        self.answers = answers


_AGENT_COMPONENTS_ATTR = "agent_components"


def _get_or_build_agent_components(request: Request) -> _AgentComponents:
    existing: _AgentComponents | None = getattr(request.app.state, _AGENT_COMPONENTS_ATTR, None)
    if existing is not None:
        return existing
    settings = request.app.state.settings
    retrieval_settings = settings.retrieval
    evidence_policy_settings = settings.evidence_policy
    embeddings = HttpEmbeddingProvider(
        base_url=retrieval_settings.embedding_base_url,
        model=retrieval_settings.embedding_model,
        timeout_seconds=retrieval_settings.embedding_timeout_seconds,
    )
    policy = DeterministicEvidencePolicy(
        policy_version=evidence_policy_settings.policy_version,
        minimum_fused_score=evidence_policy_settings.minimum_fused_score,
        minimum_score_gap=evidence_policy_settings.minimum_score_gap,
        degraded_score_multiplier=evidence_policy_settings.degraded_score_multiplier,
    )
    prompt = load_prompt_definition(settings.llm.prompt_version)
    llm = OpenAiCompatibleLlmProvider(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        timeout_seconds=settings.llm.timeout_seconds,
        prompt=prompt,
    )
    answers = AnswerGenerator(provider=llm)
    components = _AgentComponents(embeddings=embeddings, policy=policy, answers=answers)
    setattr(request.app.state, _AGENT_COMPONENTS_ATTR, components)
    return components
