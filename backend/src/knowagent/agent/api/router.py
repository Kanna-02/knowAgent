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
from knowagent.agent.application.conversation_service import (
    REWRITE_CONTEXT_HISTORY_LIMIT,
    ConversationService,
)
from knowagent.agent.application.evidence_decision import DeterministicEvidencePolicy
from knowagent.agent.application.query_rewriter import QueryRewriter
from knowagent.agent.application.reliable_question import ReliableQuestionService
from knowagent.agent.domain.conversation import (
    DEFAULT_RETRIEVAL_PROFILE_NAME,
    DEFAULT_RETRIEVAL_PROFILE_VERSION,
    ConversationMessageRole,
    QueryRewriteResult,
    QueryRewriteTurn,
)
from knowagent.agent.domain.models import (
    EvidenceBundle,
    EvidenceDecision,
    PromptDefinition,
    QuestionResolution,
    QuestionStreamEvent,
    QuestionStreamEventKind,
    VerifiedAnswer,
)
from knowagent.agent.infrastructure.openai_compatible import OpenAiCompatibleLlmProvider
from knowagent.agent.infrastructure.prompt_repository import PromptRepository
from knowagent.agent.infrastructure.retrieval_profile_repository import (
    RetrievalProfileRepository,
)
from knowagent.agent.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAnswerSnapshotRepository,
)
from knowagent.agent.prompts import (
    GROUNDED_ANSWER_SCENARIO,
    QUERY_REWRITE_SCENARIO,
    load_prompt_definition,
)
from knowagent.common.errors import (
    KnowAgentError,
    NotFoundError,
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


def _resolve_active_prompts(
    database: Session,
    *,
    request: Request | None = None,
) -> tuple[PromptDefinition | None, PromptDefinition | None]:
    """Resolve the active prompt definitions for each supported scenario.

    Returns ``(answer_prompt, rewrite_prompt)`` for the caller to apply via
    ``OpenAiCompatibleLlmProvider.with_prompt_definition`` on a per-request
    copy. Scenarios without an enabled row keep the packaged prompt loaded at
    process startup; the shared provider itself is never mutated, so
    concurrent requests cannot overwrite each other's prompt selection.

    When ``request`` is supplied the resolved prompts are cached on
    ``request.state`` so subsequent calls in the same request (e.g. by
    ``_build_question_service`` and ``_maybe_rewrite_query``) reuse the same
    result rather than issuing redundant SELECT queries.
    """
    if request is not None:
        cached: tuple[PromptDefinition | None, PromptDefinition | None] | None = getattr(
            request.state, _ACTIVE_PROMPTS_ATTR, None
        )
        if cached is not None:
            return cached
    repository = PromptRepository(database)
    answer_prompt = repository.get_active(GROUNDED_ANSWER_SCENARIO)
    rewrite_prompt = repository.get_active(QUERY_REWRITE_SCENARIO)
    pair: tuple[PromptDefinition | None, PromptDefinition | None] = (
        answer_prompt,
        rewrite_prompt,
    )
    if request is not None:
        setattr(request.state, _ACTIVE_PROMPTS_ATTR, pair)
    return pair


def _build_request_llm(
    shared_llm: OpenAiCompatibleLlmProvider,
    *,
    answer_prompt: PromptDefinition | None,
    rewrite_prompt: PromptDefinition | None,
) -> OpenAiCompatibleLlmProvider:
    """Return an immutable per-request LLM copy bound to the resolved prompts.

    Falls back to the packaged prompt loaded at process startup when the
    database has no enabled row for a scenario. The HTTP client and
    configuration are shared with ``shared_llm`` so the connection pool is
    reused; only the active prompt fields are replaced on the copy.
    """
    llm = shared_llm
    if answer_prompt is not None:
        llm = llm.with_prompt_definition(answer_prompt)
    if rewrite_prompt is not None:
        llm = llm.with_prompt_definition(rewrite_prompt)
    return llm


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


async def _stream_resolution(  # pylint: disable=too-many-arguments
    question_service: ReliableQuestionService,
    *,
    run_id: UUID,
    requester_id: UUID,
    system_id: UUID,
    question: str,
    required_terms: tuple[str, ...],
    conversation_id: UUID | None = None,
    retrieval_profile: str | None = None,
    database: Session | None = None,
    request: Request | None = None,
) -> AsyncIterator[bytes]:
    # The retrieval profile has already been applied to ``question_service`` by
    # ``_build_question_service`` before this iterator starts, so the parameter
    # is unused here. It is kept in the signature so the SSE authorizer can pass
    # it through from the minted token for future stream-time reauthorization.
    del retrieval_profile
    rewrite = None
    if conversation_id is not None and database is not None and request is not None:
        rewrite = await _maybe_rewrite_query_safe(
            database=database,
            system_id=system_id,
            account_id=requester_id,
            question=question,
            conversation_id=conversation_id,
            request=request,
        )
    # Persist the user question before the first stream event is yielded, so
    # it survives even if the client disconnects mid-stream or the provider
    # becomes unavailable.
    if conversation_id is not None and database is not None:
        _persist_stream_user_turn(
            database=database,
            system_id=system_id,
            account_id=requester_id,
            conversation_id=conversation_id,
            question=question,
            rewrite=rewrite,
            now=datetime.now(UTC),
        )
    try:
        async for event in question_service.resolve_stream(
            run_id=run_id,
            requester_id=requester_id,
            system_id=system_id,
            question=question,
            required_terms=required_terms,
            rewrite=rewrite,
        ):
            if conversation_id is not None and database is not None:
                _persist_stream_terminal_turn(
                    database=database,
                    system_id=system_id,
                    account_id=requester_id,
                    conversation_id=conversation_id,
                    event=event,
                    now=datetime.now(UTC),
                )
            if event.kind is QuestionStreamEventKind.RETRIEVAL_STARTED and rewrite is not None:
                rendered = _render_event(
                    event,
                    system_id=system_id,
                    question=question,
                    rewritten_query=rewrite.rewritten_query,
                    intent=rewrite.intent,
                    rewrite_prompt_version=rewrite.prompt_version,
                    retrieval_profile_name=question_service.retrieval_profile_name,
                    retrieval_profile_version=question_service.retrieval_profile_version,
                )
            else:
                rendered = _render_event(
                    event,
                    system_id=system_id,
                    question=question,
                    retrieval_profile_name=question_service.retrieval_profile_name,
                    retrieval_profile_version=question_service.retrieval_profile_version,
                )
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
    except Exception:  # pylint: disable=broad-exception-caught
        # A generator exception otherwise closes the SSE connection without a
        # terminal event, leaving clients stuck in the retrieval phase forever.
        LOGGER.exception("Unexpected question stream failure", extra={"run_id": str(run_id)})
        yield _format_sse(
            StreamErrorEvent(
                run_id=run_id,
                code="QUESTION_STREAM_FAILED",
                message="问答服务暂时不可用，请稍后重试",
            )
        )


def _render_event(
    event: QuestionStreamEvent,
    *,
    system_id: UUID,
    question: str,
    rewritten_query: str | None = None,
    intent: str | None = None,
    rewrite_prompt_version: str | None = None,
    retrieval_profile_name: str | None = None,
    retrieval_profile_version: str | None = None,
) -> bytes | None:
    if event.kind is QuestionStreamEventKind.RETRIEVAL_STARTED:
        return _format_sse(
            RetrievalStartedEvent(
                run_id=event.run_id,
                system_id=system_id,
                question=question,
                rewritten_query=rewritten_query,
                intent=intent,
                rewrite_prompt_version=rewrite_prompt_version,
                retrieval_profile_name=retrieval_profile_name,
                retrieval_profile_version=retrieval_profile_version,
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
                retrieval_profile_name=decision.retrieval_profile_name,
                retrieval_profile_version=decision.retrieval_profile_version,
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
    now = datetime.now(UTC)
    rewrite = await _maybe_rewrite_query(
        database=database,
        system_id=payload.system_id,
        account_id=context.account.id,
        question=payload.question,
        conversation_id=payload.conversation_id,
        components=_get_or_build_agent_components(request),
        request=request,
    )
    question_service = _build_question_service(
        request,
        database,
        retrieval_profile_name=payload.retrieval_profile,
    )
    resolution = await question_service.resolve(
        run_id=run_id,
        requester_id=context.account.id,
        system_id=payload.system_id,
        question=payload.question,
        required_terms=payload.required_terms_tuple,
        rewrite=rewrite,
    )
    if payload.conversation_id is not None:
        _persist_conversation_turn(
            database=database,
            system_id=payload.system_id,
            account_id=context.account.id,
            conversation_id=payload.conversation_id,
            question=payload.question,
            rewrite=rewrite,
            resolution=resolution,
            now=now,
        )
    return QuestionResponse.from_resolution(resolution)


async def _maybe_rewrite_query(  # pylint: disable=too-many-arguments
    *,
    database: Session,
    system_id: UUID,
    account_id: UUID,
    question: str,
    conversation_id: UUID | None,
    components: _AgentComponents,
    request: Request | None = None,
) -> QueryRewriteResult | None:
    """Classify intent and rewrite follow-up questions using conversation history.

    Returns ``None`` when no conversation is specified. When the conversation
    has no prior history the question is treated as standalone. LLM failures
    degrade gracefully to the original question with a standalone intent.
    """
    if conversation_id is None:
        return None
    answer_prompt, rewrite_prompt = _resolve_active_prompts(database=database, request=request)
    local_llm = _build_request_llm(
        components.llm,
        answer_prompt=answer_prompt,
        rewrite_prompt=rewrite_prompt,
    )
    conversation_service = ConversationService(database)
    # Conversations are personal even when several users can access a system.
    conversation_service.get_conversation(
        conversation_id=conversation_id,
        system_id=system_id,
        account_id=account_id,
    )
    history_messages = conversation_service.list_messages(
        conversation_id=conversation_id,
        system_id=system_id,
        limit=REWRITE_CONTEXT_HISTORY_LIMIT,
    )
    history = tuple(
        QueryRewriteTurn(role=message.role, content=message.content) for message in history_messages
    )
    rewriter = QueryRewriter(provider=local_llm)
    return await rewriter.rewrite(
        question=question,
        history_turns=history,
    )


async def _maybe_rewrite_query_safe(
    *,
    database: Session,
    system_id: UUID,
    account_id: UUID,
    question: str,
    conversation_id: UUID | None,
    request: Request,
) -> QueryRewriteResult | None:
    """Stream-safe variant that reads shared components from app state.

    The SSE stream consumer runs after the POST mint, so it cannot rely on the
    request-scoped component resolution used by ``ask_question``. This helper
    reads the shared components from app state instead.
    """
    if conversation_id is None:
        return None
    components = _get_or_build_agent_components(request)
    return await _maybe_rewrite_query(
        database=database,
        system_id=system_id,
        account_id=account_id,
        question=question,
        conversation_id=conversation_id,
        components=components,
        request=request,
    )


def _persist_conversation_turn(  # pylint: disable=too-many-arguments
    *,
    database: Session,
    system_id: UUID,
    account_id: UUID,
    conversation_id: UUID,
    question: str,
    rewrite: QueryRewriteResult | None,
    resolution: QuestionResolution,
    now: datetime,
) -> None:
    """Persist the user question and assistant answer to the conversation."""
    service = ConversationService(database)
    service.get_conversation(
        conversation_id=conversation_id,
        system_id=system_id,
        account_id=account_id,
    )
    service.append_message(
        conversation_id=conversation_id,
        system_id=system_id,
        role=ConversationMessageRole.USER,
        content=question,
        intent=rewrite.intent if rewrite is not None else None,
        rewritten_query=rewrite.rewritten_query if rewrite is not None else None,
        rewrite_prompt_version=rewrite.prompt_version if rewrite is not None else None,
        now=now,
    )
    if resolution.answer is not None:
        service.append_message(
            conversation_id=conversation_id,
            system_id=system_id,
            role=ConversationMessageRole.ASSISTANT,
            content=resolution.answer.text,
            now=now,
        )


def _persist_stream_terminal_turn(
    *,
    database: Session,
    system_id: UUID,
    account_id: UUID,
    conversation_id: UUID,
    event: QuestionStreamEvent,
    now: datetime,
) -> None:
    """Persist the assistant answer when the stream reaches a terminal event.

    The user question is already persisted in the stream prelude by
    ``_persist_stream_user_turn``, so this function only appends the
    assistant message on ``ANSWER_COMPLETED``. ``REFUSED`` events do not
    produce an assistant message; the refusal ticket is recorded separately.
    """
    if event.kind not in {
        QuestionStreamEventKind.ANSWER_COMPLETED,
        QuestionStreamEventKind.REFUSED,
    }:
        return
    service = ConversationService(database)
    service.get_conversation(
        conversation_id=conversation_id,
        system_id=system_id,
        account_id=account_id,
    )
    if event.kind is QuestionStreamEventKind.ANSWER_COMPLETED:
        answer = event.payload
        if not isinstance(answer, VerifiedAnswer):
            raise TypeError(
                f"ANSWER_COMPLETED event payload must be VerifiedAnswer, "
                f"got {type(answer).__name__}"
            )
        service.append_message(
            conversation_id=conversation_id,
            system_id=system_id,
            role=ConversationMessageRole.ASSISTANT,
            content=answer.text,
            now=now,
        )


def _persist_stream_user_turn(  # pylint: disable=too-many-arguments
    *,
    database: Session,
    system_id: UUID,
    account_id: UUID,
    conversation_id: UUID,
    question: str,
    rewrite: QueryRewriteResult | None,
    now: datetime,
) -> None:
    """Persist the user question at the start of an SSE stream.

    Called before the first stream event is yielded, so the user question is
    preserved even if the client disconnects mid-stream or the LLM provider
    becomes unavailable. The assistant answer is persisted separately on
    ``ANSWER_COMPLETED`` by ``_persist_stream_terminal_turn``.
    """
    service = ConversationService(database)
    service.get_conversation(
        conversation_id=conversation_id,
        system_id=system_id,
        account_id=account_id,
    )
    service.append_message(
        conversation_id=conversation_id,
        system_id=system_id,
        role=ConversationMessageRole.USER,
        content=question,
        intent=rewrite.intent if rewrite is not None else None,
        rewritten_query=rewrite.rewritten_query if rewrite is not None else None,
        rewrite_prompt_version=rewrite.prompt_version if rewrite is not None else None,
        now=now,
    )


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
    *,
    retrieval_profile_name: str | None = None,
) -> ReliableQuestionService:
    settings = request.app.state.settings
    retrieval_settings = settings.retrieval
    ticket_settings = settings.tickets

    components = _get_or_build_agent_components(request)
    answer_prompt, rewrite_prompt = _resolve_active_prompts(database=database, request=request)
    local_llm = _build_request_llm(
        components.llm,
        answer_prompt=answer_prompt,
        rewrite_prompt=rewrite_prompt,
    )

    # An explicit profile name must resolve; the implicit default may use the
    # packaged settings fallback before the seed migration has run.
    profile_repository = RetrievalProfileRepository(database)
    requested_profile_name = retrieval_profile_name or DEFAULT_RETRIEVAL_PROFILE_NAME
    profile = profile_repository.get_active(requested_profile_name)
    if retrieval_profile_name is not None and profile is None:
        raise NotFoundError(
            "RETRIEVAL_PROFILE_NOT_FOUND",
            "检索配置不存在或未激活",
        )
    effective_profile_name = profile.name if profile is not None else DEFAULT_RETRIEVAL_PROFILE_NAME
    effective_profile_version = (
        profile.version if profile is not None else DEFAULT_RETRIEVAL_PROFILE_VERSION
    )

    embeddings = components.embeddings
    search = PostgresKnowledgeSearch(database)
    keyword_top_k = (
        profile.keyword_top_k if profile is not None else retrieval_settings.keyword_top_k
    )
    vector_top_k = profile.vector_top_k if profile is not None else retrieval_settings.vector_top_k
    result_top_k = profile.result_top_k if profile is not None else retrieval_settings.result_top_k
    rrf_k = profile.rrf_k if profile is not None else retrieval_settings.rrf_k
    keyword_weight = (
        profile.keyword_weight if profile is not None else retrieval_settings.keyword_weight
    )
    vector_weight = (
        profile.vector_weight if profile is not None else retrieval_settings.vector_weight
    )
    rerank_candidate_top_k = (
        profile.rerank_candidate_top_k
        if profile is not None
        else retrieval_settings.rerank_candidate_top_k
    )
    rerank_top_k = profile.rerank_top_k if profile is not None else retrieval_settings.rerank_top_k
    evidence_max_items = (
        profile.evidence_max_items if profile is not None else retrieval_settings.evidence_max_items
    )
    evidence_max_characters = (
        profile.evidence_max_characters
        if profile is not None
        else retrieval_settings.evidence_max_characters
    )
    retrieval = BasicRetrievalService(
        embeddings=embeddings,
        lexical=search,
        vectors=search,
        keyword_top_k=keyword_top_k,
        vector_top_k=vector_top_k,
        result_top_k=result_top_k,
        rrf_k=rrf_k,
        metrics=_NoopMetrics(),
        reranker=components.reranker,
        rerank_candidate_top_k=rerank_candidate_top_k,
        rerank_top_k=rerank_top_k,
        keyword_weight=keyword_weight,
        vector_weight=vector_weight,
    )
    evidence = EvidenceOrganizer(
        max_items=evidence_max_items,
        max_characters=evidence_max_characters,
    )
    policy = components.policy
    answers = AnswerGenerator(provider=local_llm)
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
        retrieval_profile_name=effective_profile_name,
        retrieval_profile_version=effective_profile_version,
    )


class _AgentComponents:  # pylint: disable=too-few-public-methods
    """Process-wide, request-independent objects backing question answering.

    The LLM and Embedding providers hold HTTP connection pools that are
    expensive to build per request. ``EvidenceOrganizer``/``AnswerGenerator``
    and the prompt definition are also stateless. They are created once per app
    process and reused across requests, while the SQLAlchemy Session stays
    request-scoped.
    """

    __slots__ = ("embeddings", "reranker", "policy", "answers", "llm")

    def __init__(
        self,
        *,
        embeddings: HttpEmbeddingProvider,
        reranker: HttpRerankProvider,
        policy: DeterministicEvidencePolicy,
        answers: AnswerGenerator,
        llm: OpenAiCompatibleLlmProvider,
    ) -> None:
        self.embeddings = embeddings
        self.reranker = reranker
        self.policy = policy
        self.answers = answers
        self.llm = llm


_AGENT_COMPONENTS_ATTR = "agent_components"

# Per-request cache of active prompt definitions. The two scenarios are read
# on every question request and stream event, but the active prompt set
# does not change within a single request, so we cache it on ``request.state``
# after the first resolution.
_ACTIVE_PROMPTS_ATTR = "active_prompts"


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
        failure_cooldown_seconds=retrieval_settings.rerank_failure_cooldown_seconds,
    )
    policy = DeterministicEvidencePolicy(
        policy_version=evidence_policy_settings.policy_version,
        minimum_fused_score=evidence_policy_settings.minimum_fused_score,
        minimum_score_gap=evidence_policy_settings.minimum_score_gap,
        degraded_score_multiplier=evidence_policy_settings.degraded_score_multiplier,
    )
    prompt = load_prompt_definition(settings.llm.prompt_version)
    rewrite_prompt = load_prompt_definition(settings.llm.rewrite_prompt_version)
    llm = OpenAiCompatibleLlmProvider(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        timeout_seconds=settings.llm.timeout_seconds,
        prompt=prompt,
        rewrite_prompt=rewrite_prompt,
    )
    answers = AnswerGenerator(provider=llm)
    components = _AgentComponents(
        embeddings=embeddings,
        reranker=reranker,
        policy=policy,
        answers=answers,
        llm=llm,
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
        conversation_id=payload.conversation_id,
        retrieval_profile=payload.retrieval_profile,
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
    conversation_id = stored.conversation_id
    retrieval_profile = stored.retrieval_profile
    question_service = _build_question_service(
        request,
        database,
        retrieval_profile_name=retrieval_profile,
    )

    async def event_source() -> AsyncIterator[bytes]:
        async for chunk in _stream_resolution(
            question_service,
            run_id=run_id,
            requester_id=context.account.id,
            system_id=system_id,
            question=question,
            required_terms=required_terms,
            conversation_id=conversation_id,
            retrieval_profile=retrieval_profile,
            database=database,
            request=request,
        ):
            yield chunk

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
