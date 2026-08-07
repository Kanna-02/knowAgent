from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from sqlalchemy.orm import Session

from knowagent.agent.api.admin_schemas import (
    ActivatePromptRequest,
    ActivateRetrievalProfileRequest,
    PromptDefinitionPage,
    PromptDefinitionView,
    RetrievalProfilePage,
    RetrievalProfileView,
    SavePromptDefinitionRequest,
    SaveRetrievalProfileRequest,
)
from knowagent.agent.domain.conversation import RetrievalProfile
from knowagent.agent.domain.models import PromptDefinition
from knowagent.agent.infrastructure.prompt_repository import PromptRepository
from knowagent.agent.infrastructure.retrieval_profile_repository import (
    RetrievalProfileRepository,
)
from knowagent.common.errors import NotFoundError, ValidationError
from knowagent.identity.api.dependencies import AdminContext, AdminCsrfContext, DatabaseSession
from knowagent.identity.infrastructure.sqlalchemy_repository import SqlAlchemyAuditSink

router = APIRouter()

PromptScenario = Literal["grounded_answer", "query_rewrite"]


@router.get("/admin/prompt-definitions", response_model=PromptDefinitionPage)
def list_prompt_definitions(
    context: AdminContext,
    database: DatabaseSession,
    scenario: Annotated[PromptScenario | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PromptDefinitionPage:
    del context
    items, total = PromptRepository(database).list_page(
        scenario=scenario,
        page=page,
        page_size=page_size,
    )
    return PromptDefinitionPage(
        items=[_prompt_view(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/admin/prompt-definitions/{scenario}/{version}",
    response_model=PromptDefinitionView,
)
def get_prompt_definition(
    scenario: PromptScenario,
    version: str,
    context: AdminContext,
    database: DatabaseSession,
) -> PromptDefinitionView:
    del context
    return _prompt_view(PromptRepository(database).get_version(scenario, version))


@router.post(
    "/admin/prompt-definitions",
    response_model=PromptDefinitionView,
    status_code=status.HTTP_201_CREATED,
)
def save_prompt_definition(
    payload: SavePromptDefinitionRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> PromptDefinitionView:
    try:
        definition = PromptDefinition(
            scenario=payload.scenario,
            version=payload.version.strip(),
            content=payload.content.strip(),
            enabled=False,
            created_at=datetime.now(UTC),
            change_note=payload.change_note.strip(),
        )
    except ValueError as error:
        raise ValidationError("PROMPT_DEFINITION_INVALID", "提示词版本内容无效") from error
    saved = PromptRepository(database).save(definition)
    _record_configuration_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="prompt.create",
        object_type="prompt_definition",
        name=saved.scenario,
        version=saved.version,
    )
    return _prompt_view(saved)


@router.post(
    "/admin/prompt-definitions/activate",
    response_model=PromptDefinitionView,
)
def activate_prompt_definition(
    payload: ActivatePromptRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> PromptDefinitionView:
    activated = PromptRepository(database).activate(
        payload.scenario,
        payload.version.strip(),
    )
    _record_configuration_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="prompt.activate",
        object_type="prompt_definition",
        name=activated.scenario,
        version=activated.version,
    )
    return _prompt_view(activated)


@router.get("/admin/retrieval-profiles", response_model=RetrievalProfilePage)
def list_retrieval_profiles(
    context: AdminContext,
    database: DatabaseSession,
    name: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RetrievalProfilePage:
    del context
    items, total = RetrievalProfileRepository(database).list_page(
        name=name.strip() if name is not None else None,
        page=page,
        page_size=page_size,
    )
    return RetrievalProfilePage(
        items=[_profile_view(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/admin/retrieval-profiles/{name}/{version}",
    response_model=RetrievalProfileView,
)
def get_retrieval_profile(
    name: str,
    version: str,
    context: AdminContext,
    database: DatabaseSession,
) -> RetrievalProfileView:
    del context
    profile = RetrievalProfileRepository(database).get_version(name.strip(), version.strip())
    if profile is None:
        raise NotFoundError("RETRIEVAL_PROFILE_NOT_FOUND", "检索配置版本不存在")
    return _profile_view(profile)


@router.post(
    "/admin/retrieval-profiles",
    response_model=RetrievalProfileView,
    status_code=status.HTTP_201_CREATED,
)
def save_retrieval_profile(
    payload: SaveRetrievalProfileRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> RetrievalProfileView:
    try:
        profile = RetrievalProfile(
            name=payload.name.strip(),
            version=payload.version.strip(),
            keyword_top_k=payload.keyword_top_k,
            vector_top_k=payload.vector_top_k,
            result_top_k=payload.result_top_k,
            rrf_k=payload.rrf_k,
            keyword_weight=payload.keyword_weight,
            vector_weight=payload.vector_weight,
            rerank_candidate_top_k=payload.rerank_candidate_top_k,
            rerank_top_k=payload.rerank_top_k,
            evidence_max_items=payload.evidence_max_items,
            evidence_max_characters=payload.evidence_max_characters,
            is_active=False,
            created_at=datetime.now(UTC),
            change_note=payload.change_note.strip(),
        )
    except ValueError as error:
        raise ValidationError("RETRIEVAL_PROFILE_INVALID", "检索配置参数无效") from error
    saved = RetrievalProfileRepository(database).save(profile)
    _record_configuration_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="retrieval_profile.create",
        object_type="retrieval_profile",
        name=saved.name,
        version=saved.version,
    )
    return _profile_view(saved)


@router.post(
    "/admin/retrieval-profiles/activate",
    response_model=RetrievalProfileView,
)
def activate_retrieval_profile(
    payload: ActivateRetrievalProfileRequest,
    request: Request,
    context: AdminCsrfContext,
    database: DatabaseSession,
) -> RetrievalProfileView:
    activated = RetrievalProfileRepository(database).activate(
        payload.name.strip(),
        payload.version.strip(),
    )
    _record_configuration_audit(
        database=database,
        request=request,
        actor_id=context.account.id,
        action="retrieval_profile.activate",
        object_type="retrieval_profile",
        name=activated.name,
        version=activated.version,
    )
    return _profile_view(activated)


def _record_configuration_audit(
    *,
    database: Session,
    request: Request,
    actor_id: UUID,
    action: str,
    object_type: str,
    name: str,
    version: str,
) -> None:
    SqlAlchemyAuditSink(database).record(
        action,
        "success",
        actor_id=actor_id,
        object_type=object_type,
        request_id=request.state.request_id,
        metadata={"name": name, "version": version},
    )


def _prompt_view(definition: PromptDefinition) -> PromptDefinitionView:
    return PromptDefinitionView(
        scenario=definition.scenario,
        version=definition.version,
        content=definition.content,
        enabled=definition.enabled,
        created_at=definition.created_at,
        change_note=definition.change_note,
    )


def _profile_view(profile: RetrievalProfile) -> RetrievalProfileView:
    return RetrievalProfileView(
        name=profile.name,
        version=profile.version,
        keyword_top_k=profile.keyword_top_k,
        vector_top_k=profile.vector_top_k,
        result_top_k=profile.result_top_k,
        rrf_k=profile.rrf_k,
        keyword_weight=profile.keyword_weight,
        vector_weight=profile.vector_weight,
        rerank_candidate_top_k=profile.rerank_candidate_top_k,
        rerank_top_k=profile.rerank_top_k,
        evidence_max_items=profile.evidence_max_items,
        evidence_max_characters=profile.evidence_max_characters,
        is_active=profile.is_active,
        created_at=profile.created_at,
        change_note=profile.change_note,
    )
