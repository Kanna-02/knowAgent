from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowagent.agent.domain.models import (
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
    QuestionResolution,
    QuestionResolutionStatus,
)
from knowagent.documents.domain.models import SourceLocator


class QuestionRequest(BaseModel):
    system_id: UUID
    question: str = Field(min_length=1, max_length=2000)
    required_terms: list[str] = Field(default_factory=list, max_length=20)

    @property
    def required_terms_tuple(self) -> tuple[str, ...]:
        return tuple(self.required_terms)


class LocatorView(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    document_id: UUID | None = None
    document_version_id: UUID | None = None
    source_type: str
    block_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    bounding_box: tuple[float, float, float, float] | None = None
    heading_path: tuple[str, ...] = ()
    paragraph_start: int | None = Field(default=None, ge=1)
    paragraph_end: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    table_index: int | None = Field(default=None, ge=1)
    table_row_start: int | None = Field(default=None, ge=1)
    table_row_end: int | None = Field(default=None, ge=1)
    sheet_name: str | None = None
    cell_range: str | None = None
    ticket_id: UUID | None = None

    @classmethod
    def from_locator(cls, locator: SourceLocator) -> LocatorView:
        return cls(
            document_id=locator.document_id,
            document_version_id=locator.document_version_id,
            source_type=locator.source_type.value,
            block_index=locator.block_index,
            page_number=locator.page_number,
            bounding_box=locator.bounding_box,
            heading_path=locator.heading_path,
            paragraph_start=locator.paragraph_start,
            paragraph_end=locator.paragraph_end,
            line_start=locator.line_start,
            line_end=locator.line_end,
            table_index=locator.table_index,
            table_row_start=locator.table_row_start,
            table_row_end=locator.table_row_end,
            sheet_name=locator.sheet_name,
            cell_range=locator.cell_range,
            ticket_id=locator.ticket_id,
        )


class CitationView(BaseModel):
    rank: int = Field(ge=1)
    claim_rank: int = Field(ge=1)
    chunk_id: UUID
    source_id: UUID
    source_name: str
    source_version: str
    quoted_text: str
    locators: tuple[LocatorView, ...]


class ClaimView(BaseModel):
    rank: int = Field(ge=1)
    text: str
    citation_ranks: tuple[int, ...]


class AnswerView(BaseModel):
    text: str
    claims: tuple[ClaimView, ...]
    citations: tuple[CitationView, ...]
    model: str
    prompt_version: str


class QuestionResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    run_id: UUID
    status: QuestionResolutionStatus
    answer: AnswerView | None = None
    ticket_id: UUID | None = None
    reason_codes: tuple[EvidenceReasonCode, ...] = ()
    degraded_reasons: tuple[str, ...] = ()
    decision_outcome: EvidenceDecisionOutcome
    policy_version: str
    decided_at: datetime

    @classmethod
    def from_resolution(cls, resolution: QuestionResolution) -> QuestionResponse:
        decision = resolution.decision
        answer_view = None
        if resolution.answer is not None:
            answer_view = AnswerView(
                text=resolution.answer.text,
                claims=tuple(
                    ClaimView(
                        rank=claim.rank,
                        text=claim.text,
                        citation_ranks=claim.citation_ranks,
                    )
                    for claim in resolution.answer.claims
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
                        locators=tuple(
                            LocatorView.from_locator(locator) for locator in citation.locators
                        ),
                    )
                    for citation in resolution.answer.citations
                ),
                model=resolution.answer.model,
                prompt_version=resolution.answer.prompt_version,
            )
        return cls(
            run_id=decision.run_id,
            status=resolution.status,
            answer=answer_view,
            ticket_id=resolution.ticket_id,
            reason_codes=resolution.reason_codes,
            degraded_reasons=resolution.degraded_reasons,
            decision_outcome=decision.outcome,
            policy_version=decision.policy_version,
            decided_at=decision.decided_at,
        )


class SseAuthToken(BaseModel):
    """One-time bearer token authorizing the SSE question stream.

    ``POST /api/v1/questions/stream`` returns this token; the client then opens
    ``GET /api/v1/questions/stream/events?token=<token>`` with the same session
    cookie. The token is short-lived and single-use, avoiding long-lived
    query-string credentials on the request that starts the stream.
    """

    token: str
    account_id: UUID
    run_id: UUID
    system_id: UUID
    question: str
    required_terms: tuple[str, ...] = ()
    expires_at: datetime


class EvidenceItemView(BaseModel):
    """Compact evidence preview emitted in the ``evidence_ready`` SSE event."""

    evidence_id: str
    source_name: str
    source_version: str
    quoted_text: str


class RetrievalStartedEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: str = "retrieval_started"
    run_id: UUID
    system_id: UUID
    question: str


class EvidenceReadyEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: str = "evidence_ready"
    run_id: UUID
    evidence: tuple[EvidenceItemView, ...]
    degraded_reasons: tuple[str, ...] = ()


class DecisionEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: str = "decision"
    run_id: UUID
    outcome: EvidenceDecisionOutcome
    policy_version: str
    reason_codes: tuple[EvidenceReasonCode, ...] = ()
    decided_at: datetime


class AnswerDeltaEvent(BaseModel):
    """Incremental token delta from the LLM stream."""

    model_config = ConfigDict(use_enum_values=True)

    type: str = "answer_delta"
    run_id: UUID
    delta: str


class AnswerCompletedEvent(BaseModel):
    """Final structured, grounded answer with full claims and citations."""

    model_config = ConfigDict(use_enum_values=True)

    type: str = "answer_completed"
    run_id: UUID
    answer: AnswerView
    degraded_reasons: tuple[str, ...] = ()


class RefusedEvent(BaseModel):
    """Refusal outcome carrying the ticket id created for knowledge gap tracking."""

    model_config = ConfigDict(use_enum_values=True)

    type: str = "refused"
    run_id: UUID
    ticket_id: UUID
    outcome: EvidenceDecisionOutcome
    reason_codes: tuple[EvidenceReasonCode, ...]
    policy_version: str
    decided_at: datetime
    degraded_reasons: tuple[str, ...] = ()


class StreamErrorEvent(BaseModel):
    """Terminal error event for system-level failures mid-stream.

    Knowledge-gap refusals are emitted as ``refused``; this event covers
    provider-unavailable and other infrastructure failures so the client
    can distinguish them.
    """

    model_config = ConfigDict(use_enum_values=True)

    type: str = "error"
    run_id: UUID
    code: str
    message: str
