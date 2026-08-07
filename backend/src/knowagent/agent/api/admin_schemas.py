from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateConversationRequest(BaseModel):
    system_id: UUID
    title: str = Field(min_length=1, max_length=500)


class ConversationView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    system_id: UUID
    account_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationView]
    page: int
    page_size: int
    total: int


class ConversationMessageView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    role: str
    content: str
    intent: str | None = None
    rewritten_query: str | None = None
    rewrite_prompt_version: str | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationView
    messages: list[ConversationMessageView]


class PromptDefinitionView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    scenario: str
    version: str
    content: str
    enabled: bool
    created_at: datetime
    change_note: str


class PromptDefinitionPage(BaseModel):
    items: list[PromptDefinitionView]
    page: int
    page_size: int
    total: int


class SavePromptDefinitionRequest(BaseModel):
    scenario: Literal["grounded_answer", "query_rewrite"]
    version: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=12000)
    change_note: str = Field(min_length=1, max_length=500)


class ActivatePromptRequest(BaseModel):
    scenario: Literal["grounded_answer", "query_rewrite"]
    version: str = Field(min_length=1, max_length=100)


class RetrievalProfileView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str
    version: str
    keyword_top_k: int
    vector_top_k: int
    result_top_k: int
    rrf_k: int
    keyword_weight: float
    vector_weight: float
    rerank_candidate_top_k: int
    rerank_top_k: int
    evidence_max_items: int
    evidence_max_characters: int
    is_active: bool
    created_at: datetime
    change_note: str


class RetrievalProfilePage(BaseModel):
    items: list[RetrievalProfileView]
    page: int
    page_size: int
    total: int


class SaveRetrievalProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=100)
    keyword_top_k: int = Field(ge=1)
    vector_top_k: int = Field(ge=1)
    result_top_k: int = Field(ge=1)
    rrf_k: int = Field(ge=1)
    keyword_weight: float = Field(gt=0, allow_inf_nan=False)
    vector_weight: float = Field(gt=0, allow_inf_nan=False)
    rerank_candidate_top_k: int = Field(ge=1)
    rerank_top_k: int = Field(ge=1)
    evidence_max_items: int = Field(ge=1)
    evidence_max_characters: int = Field(ge=1)
    change_note: str = Field(min_length=1, max_length=500)


class ActivateRetrievalProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=100)
