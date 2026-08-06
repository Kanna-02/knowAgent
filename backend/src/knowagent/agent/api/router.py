from __future__ import annotations

import json
import logging
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from knowagent.agent.api.schemas import (
    AnswerCompletedEvent,
    AnswerDeltaEvent,
    AnswerView,
    CitationView,
    ClaimView,
    DecisionEvent,
    EvidenceItemView,
    EvidenceReadyEvent,
    LocatorView,
    QuestionRequest,
    QuestionResponse,
    RefusedEvent,
    RetrievalStartedEvent,
    SseAuthToken,
    StreamErrorEvent,
)
from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.application.answer_snapshots import AnswerSnapshotService
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.models import (
    EvidenceBundle,
    EvidenceDecision,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.agent.infrastructure.openai_compatible import OpenAiCompatibleLlmProvider
from knowagent.agent.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAnswerSnapshotRepository,
)
from knowagent.agent.prompts import load_prompt_definition
from knowagent.common.errors import (
    KnowAgentError,
    ProviderUnavailableError,
)
from knowagent.identity.api.access import require_system_access as _require_shared
from knowagent.identity.api.dependencies import (
    AuthServiceDependency,
    CsrfContext,
    CurrentContextDependency,
    DatabaseSession,
    RedisClient,
)
from knowagent.identity.domain.models import Account, AccountRole
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.application.retrieval_service import BasicRetrievalService
from knowagent.retrieval.infrastructure.http_embedding import HttpEmbeddingProvider
from knowagent.retrieval.infrastructure.http_rerank import HttpRerankProvider
from knowagent.retrieval.infrastructure.sqlalchemy_search import PostgresKnowledgeSearch
from knowagent.tickets.application.refusal import RefusalTicketService
from knowagent.tickets.infrastructure.sqlalchemy_repository import (
    SqlAlchemyTicketRepository,
)

LOGGER = logging.getLogger(__name__)
router = APIRouter()


# SSE question streams are authorized in two steps: a CSRF-validated POST mints
# a single-use bearer token (stored in Redis), then the EventSource GET redeems
# it. EventSource cannot set custom headers, so the short-lived token (not the
# long-lived session cookie) is the credential on the stream request.
SSE_TOKEN_TTL_SECONDS = 120
SSE_TOKEN_PREFIX = "sse-question:"


def _sse_token_key(account_id: UUID, token: str) -> str:
    return f"{SSE_TOKEN_PREFIX}{account_id}:{token}"


def _consume_sse_token(redis: RedisClient, *, token: str, account_id: UUID) -> SseAuthToken | None:
    key = _sse_token_key(account_id, token)
    raw = redis.getdel(key)
    if not raw or not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        grant = SseAuthToken.model_validate(data)
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return grant if grant.account_id == account_id else None


def _to_answer_view(answer: VerifiedAnswer) -> AnswerView:
    return AnswerView(
        text=answer.text,
        claims=tuple(
            ClaimView(rank=claim.rank, text=claim.text, citation_ranks=claim.citation_ranks)
            for claim in answer.claims
        ),
        citations=tuple(
            CitationView(
                rank=citation.rank,
                claim_rank=citation.claim_rank,
                chunk_id=citation.chunk_id,
                source_id=citation.source_id,
                source_name=citation.source_name,
                source_version=citation.source_version,
                quoted_text=citation.quoted_text,
                locators=tuple(LocatorView.from_locator(locator) for locator in citation.locators),
            )
            for citation in answer.citations
        ),
        model=answer.model,
        prompt_version=answer.prompt_version,
    )


def _evidence_view(bundle: EvidenceBundle) -> tuple[EvidenceItemView, ...]:
    return tuple(
        EvidenceItemView(
            evidence_id=item.evidence_id,
            source_name=item.source_name,
            source_version=item.source_version,
            quoted_text=item.quoted_text,
        )
        for item in bundle.items
    )


def _format_sse(event: object) -> bytes:
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"data: {data}\n\n".encode("utf-8")


async def _stream_resolution(
    question_service: ReliableQuestionService,
    *,
    run_id: UUID,
    requester_id: UUID,
    system_id: UUID,
    question: str,
    required_terms: tuple[str, ...],
) -> AsyncIterator[bytes]:
    try:
        async for event in question_service.resolve_stream(
            run_id=run_id,
            requester_id=requester_id,
            system_id=system_id,
            question=question,
            required_terms=required_terms,
        ):
            rendered = _render_event(event, system_id=system_id, question=question)
            if rendered is not None:
                yield rendered
    except ProviderUnavailableError:
        yield _format_sse(
            StreamErrorEvent(
                run_id=run_id,
                code="PROVIDER_UNAVAILABLE",
                message="模型服务暂时不可用，请稍后重试",
            )
        )
    except KnowAgentError as error:
        yield _format_sse(StreamErrorEvent(run_id=run_id, code=error.code, message=error.message))


def _render_event(
    event: QuestionStreamEvent,
    *,
    system_id: UUID,
    question: str,
) -> bytes | None:
    if event.kind is QuestionStreamEventKind.RETRIEVAL_STARTED:
        return _format_sse(
            RetrievalStartedEvent(
                run_id=event.run_id,
                system_id=system_id,
                question=question,
            )
        )
    if event.kind is QuestionStreamEventKind.EVIDENCE_READY:
        bundle = event.payload
        assert isinstance(bundle, EvidenceBundle)
        return _format_sse(
            EvidenceReadyEvent(
                run_id=event.run_id,
                evidence=_evidence_view(bundle),
                degraded_reasons=event.degraded_reasons,
            )
        )
    if event.kind is QuestionStreamEventKind.DECISION:
        decision = event.payload
        assert isinstance(decision, EvidenceDecision)
        return _format_sse(
            DecisionEvent(
                run_id=event.run_id,
                outcome=decision.outcome,
                policy_version=decision.policy_version,
                reason_codes=decision.reason_codes,
                decided_at=decision.decided_at,
            )
        )
    if event.kind is QuestionStreamEventKind.ANSWER_DELTA:
        return _format_sse(AnswerDeltaEvent(run_id=event.run_id, delta=str(event.payload)))
    if event.kind is QuestionStreamEventKind.ANSWER_COMPLETED:
        answer = event.payload
        assert isinstance(answer, VerifiedAnswer)
        return _format_sse(
            AnswerCompletedEvent(
                run_id=event.run_id,
                answer=_to_answer_view(answer),
                degraded_reasons=event.degraded_reasons,
            )
        )
    if event.kind is QuestionStreamEventKind.REFUSED:
        decision = event.payload
        assert isinstance(decision, EvidenceDecision)
        return _format_sse(
            RefusedEvent(
                run_id=event.run_id,
                ticket_id=decision.ticket_id,  # type: ignore[arg-type]
                outcome=decision.outcome,
                reason_codes=decision.reason_codes,
                policy_version=decision.policy_version,
                decided_at=decision.decided_at,
                degraded_reasons=event.degraded_reasons,
            )
        )
    return None


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
        reranker=components.reranker,
        rerank_candidate_top_k=retrieval_settings.rerank_candidate_top_k,
        rerank_top_k=retrieval_settings.rerank_top_k,
        keyword_weight=retrieval_settings.keyword_weight,
        vector_weight=retrieval_settings.vector_weight,
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

    __slots__ = ("embeddings", "reranker", "policy", "answers")

    def __init__(
        self,
        *,
        embeddings: HttpEmbeddingProvider,
        reranker: HttpRerankProvider,
        policy: DeterministicEvidencePolicy,
        answers: AnswerGenerator,
    ) -> None:
        self.embeddings = embeddings
        self.reranker = reranker
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
    reranker = HttpRerankProvider(
        base_url=retrieval_settings.rerank_base_url,
        model=retrieval_settings.rerank_model,
        timeout_seconds=retrieval_settings.rerank_timeout_seconds,
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
    components = _AgentComponents(
        embeddings=embeddings,
        reranker=reranker,
        policy=policy,
        answers=answers,
    )
    setattr(request.app.state, _AGENT_COMPONENTS_ATTR, components)
    return components


@router.post("/questions/stream", response_model=SseAuthToken, status_code=status.HTTP_200_OK)
async def start_question_stream(
    payload: QuestionRequest,
    request: Request,
    context: CsrfContext,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    redis: RedisClient,
) -> SseAuthToken:
    """Mint a single-use token authorizing the SSE question stream.

    CSRF and system-access authorization happen here (POST can carry headers).
    The returned token is redeemed by the subsequent ``GET`` EventSource.
    """
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
    expires_at = datetime.now(UTC) + timedelta(seconds=SSE_TOKEN_TTL_SECONDS)
    token_value = secrets.token_urlsafe(32)
    payload_view = SseAuthToken(
        token=token_value,
        account_id=context.account.id,
        run_id=run_id,
        system_id=payload.system_id,
        question=payload.question,
        required_terms=payload.required_terms_tuple,
        expires_at=expires_at,
    )
    redis.set(
        _sse_token_key(context.account.id, token_value),
        json.dumps(payload_view.model_dump(mode="json")),
        ex=SSE_TOKEN_TTL_SECONDS,
    )
    return payload_view


@router.get("/questions/stream/events")
async def question_stream_events(  # pylint: disable=too-many-arguments
    request: Request,
    context: CurrentContextDependency,
    auth: AuthServiceDependency,
    database: DatabaseSession,
    redis: RedisClient,
    token: Annotated[str, Query(min_length=16, max_length=128)],
) -> StreamingResponse:
    """Stream question-answering events as Server-Sent Events.

    The client opens this endpoint with the ``token`` returned by
    ``POST /questions/stream`` plus the session cookie. The token is consumed
    on first read, so each stream starts exactly one resolution.
    """
    auth.authorize(
        context.account,
        allowed_roles={AccountRole.USER, AccountRole.SYSTEM_OWNER, AccountRole.ADMIN},
    )
    stored = _consume_sse_token(redis, token=token, account_id=context.account.id)
    if stored is None:
        raise KnowAgentError("SSE_TOKEN_INVALID", "流式问答令牌无效或已过期", status_code=401)
    if stored.run_id is None:
        raise KnowAgentError("SSE_TOKEN_INVALID", "流式问答令牌无效或已过期", status_code=401)
    run_id = stored.run_id
    system_id = stored.system_id
    question = stored.question
    required_terms = stored.required_terms
    # Re-check system access for the token's bound system, in case permissions
    # changed between mint and consume.
    _require_system_access(
        system_id=system_id,
        account=context.account,
        database=database,
    )
    question_service = _build_question_service(request, database)

    async def event_source() -> AsyncIterator[bytes]:
        async for chunk in _stream_resolution(
            question_service,
            run_id=run_id,
            requester_id=context.account.id,
            system_id=system_id,
            question=question,
            required_terms=required_terms,
        ):
            yield chunk

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
