from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowagent.analytics.domain.models import GapSource


class SystemOverviewView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    system_id: UUID
    question_count: int = Field(ge=0)
    refusal_count: int = Field(ge=0)
    open_ticket_count: int = Field(ge=0)
    resolved_ticket_count: int = Field(ge=0)
    total_ticket_count: int = Field(ge=0)


class FrequentQuestionView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    normalized_question: str
    occurrence_count: int = Field(ge=1)
    refusal_count: int = Field(ge=0)
    ticket_count: int = Field(ge=0)


class FrequentQuestionPage(BaseModel):
    items: list[FrequentQuestionView]
    total: int


class KnowledgeGapView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    normalized_question: str
    gap_source: GapSource
    occurrence_count: int = Field(ge=1)
    last_seen_at: datetime


class KnowledgeGapPage(BaseModel):
    items: list[KnowledgeGapView]
    total: int
