from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from knowagent.agent.domain.models import (
    CitationSnapshot,
    GenerationEventKind,
    GenerationRequest,
    VerifiedAnswer,
    VerifiedClaim,
)
from knowagent.agent.ports import LlmProvider
from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.retrieval.domain.models import EvidenceBundle, EvidenceItem


class _CitationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=32)
    quote: str = Field(min_length=1)


class _ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    citations: list[_CitationDraft]


class _AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[_ClaimDraft] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class StreamedAnswerDelta:
    """A grounded claim that is safe to expose before generation completes."""

    text: str


@dataclass(frozen=True, slots=True)
class StreamedAnswerCompleted:
    """The fully validated answer emitted after the provider completes."""

    answer: VerifiedAnswer


class AnswerGenerator:  # pylint: disable=too-few-public-methods
    def __init__(self, provider: LlmProvider) -> None:
        self._provider = provider

    async def generate_stream(
        self, *, question: str, evidence: EvidenceBundle
    ) -> AsyncIterator[StreamedAnswerDelta | StreamedAnswerCompleted]:
        """Yield individually grounded claims, then the complete verified answer."""
        if not evidence.items:
            raise ValidationError("ANSWER_EVIDENCE_EMPTY", "没有可用于回答的证据")
        parts: list[str] = []
        completed_count = 0
        emitted_claims = 0
        async for event in self._provider.generate(
            request=GenerationRequest(question=question, evidence=evidence)
        ):
            if event.kind is GenerationEventKind.DELTA:
                if completed_count:
                    raise ProviderUnavailableError("llm")
                parts.append(event.text)
                partial_claims = self._extract_complete_claims("".join(parts))
                for claim in partial_claims[emitted_claims:]:
                    claims, _ = self._validate_claims(_AnswerDraft(claims=[claim]), evidence.items)
                    prefix = "\n" if emitted_claims else ""
                    yield StreamedAnswerDelta(text=f"{prefix}{claims[0].text}")
                    emitted_claims += 1
            elif event.kind is GenerationEventKind.COMPLETED:
                completed_count += 1
        if completed_count != 1:
            raise ProviderUnavailableError("llm")

        draft = self._parse_draft("".join(parts))
        claims, citations = self._validate_claims(draft, evidence.items)
        for verified_claim in claims[emitted_claims:]:
            prefix = "\n" if emitted_claims else ""
            yield StreamedAnswerDelta(text=f"{prefix}{verified_claim.text}")
            emitted_claims += 1
        answer = VerifiedAnswer(
            text="\n".join(claim.text for claim in claims),
            claims=claims,
            citations=citations,
            model=self._provider.model,
            prompt_version=self._provider.prompt_version,
        )
        yield StreamedAnswerCompleted(answer=answer)

    async def generate(self, *, question: str, evidence: EvidenceBundle) -> VerifiedAnswer:
        if not evidence.items:
            raise ValidationError("ANSWER_EVIDENCE_EMPTY", "没有可用于回答的证据")
        parts: list[str] = []
        completed_count = 0
        async for event in self._provider.generate(
            request=GenerationRequest(question=question, evidence=evidence)
        ):
            if event.kind is GenerationEventKind.DELTA:
                if completed_count:
                    raise ProviderUnavailableError("llm")
                parts.append(event.text)
            elif event.kind is GenerationEventKind.COMPLETED:
                completed_count += 1
        if completed_count != 1:
            raise ProviderUnavailableError("llm")

        draft = self._parse_draft("".join(parts))
        claims, citations = self._validate_claims(draft, evidence.items)
        return VerifiedAnswer(
            text="\n".join(claim.text for claim in claims),
            claims=claims,
            citations=citations,
            model=self._provider.model,
            prompt_version=self._provider.prompt_version,
        )

    @staticmethod
    def _parse_draft(content: str) -> _AnswerDraft:
        try:
            payload = json.loads(content)
            return _AnswerDraft.model_validate(payload)
        except (json.JSONDecodeError, PydanticValidationError) as error:
            raise ValidationError("ANSWER_FORMAT_INVALID", "回答格式无效，无法验证引用") from error

    @staticmethod
    def _extract_complete_claims(content: str) -> tuple[_ClaimDraft, ...]:
        match = re.search(r'"claims"\s*:\s*\[', content)
        if match is None:
            return ()
        decoder = json.JSONDecoder()
        offset = match.end()
        claims: list[_ClaimDraft] = []
        while offset < len(content):
            while offset < len(content) and content[offset] in " \t\r\n,":
                offset += 1
            if offset >= len(content) or content[offset] == "]":
                break
            try:
                payload, offset = decoder.raw_decode(content, offset)
                claims.append(_ClaimDraft.model_validate(payload))
            except json.JSONDecodeError:
                break
            except PydanticValidationError as error:
                raise ValidationError(
                    "ANSWER_FORMAT_INVALID", "回答格式无效，无法验证引用"
                ) from error
        return tuple(claims)

    @staticmethod
    def _validate_claims(
        draft: _AnswerDraft,
        evidence_items: tuple[EvidenceItem, ...],
    ) -> tuple[tuple[VerifiedClaim, ...], tuple[CitationSnapshot, ...]]:
        evidence_by_id = {item.evidence_id: item for item in evidence_items}
        verified_claims: list[VerifiedClaim] = []
        snapshots: list[CitationSnapshot] = []
        for claim_rank, claim in enumerate(draft.claims, start=1):
            if not claim.citations:
                raise ValidationError("ANSWER_CITATION_REQUIRED", "回答声明必须包含有效引用")
            claim_text = claim.text.strip()
            if not claim_text:
                raise ValidationError("ANSWER_CLAIM_EMPTY", "回答声明不能为空")
            citation_ranks: list[int] = []
            seen_ids: set[str] = set()
            for citation in claim.citations:
                evidence = evidence_by_id.get(citation.evidence_id)
                if evidence is None:
                    raise ValidationError("ANSWER_CITATION_UNKNOWN", "回答包含未知引用")
                quote = citation.quote.strip()
                if not quote or quote not in evidence.quoted_text:
                    raise ValidationError("ANSWER_CITATION_UNSUPPORTED", "回答引用无法由证据验证")
                if claim_text not in quote:
                    raise ValidationError("ANSWER_CLAIM_UNSUPPORTED", "回答声明无法由引用支撑")
                if citation.evidence_id in seen_ids:
                    continue
                seen_ids.add(citation.evidence_id)
                snapshot_rank = len(snapshots) + 1
                citation_ranks.append(snapshot_rank)
                snapshots.append(
                    CitationSnapshot(
                        rank=snapshot_rank,
                        claim_rank=claim_rank,
                        chunk_id=evidence.chunk_id,
                        source_id=evidence.source_id,
                        source_name=evidence.source_name,
                        source_version=evidence.source_version,
                        quoted_text=quote,
                        locators=evidence.locators,
                    )
                )
            verified_claims.append(
                VerifiedClaim(
                    rank=claim_rank,
                    text=claim_text,
                    citation_ranks=tuple(citation_ranks),
                )
            )
        return tuple(verified_claims), tuple(snapshots)
