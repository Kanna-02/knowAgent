from __future__ import annotations

import math
import unicodedata
from datetime import datetime
from uuid import UUID, uuid4

from knowagent.agent.domain.models import (
    EvidenceCandidateSummary,
    EvidenceDecision,
    EvidenceDecisionOutcome,
    EvidenceReasonCode,
)
from knowagent.retrieval.domain.models import RetrievalResult


class DeterministicEvidencePolicy:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        policy_version: str,
        minimum_fused_score: float,
        minimum_score_gap: float,
        degraded_score_multiplier: float,
    ) -> None:
        if not policy_version.strip():
            raise ValueError("evidence policy version must not be blank")
        numeric_values = (minimum_fused_score, minimum_score_gap, degraded_score_multiplier)
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("evidence policy numeric values must be finite")
        if minimum_fused_score < 0 or minimum_score_gap < 0:
            raise ValueError("evidence score thresholds must not be negative")
        if degraded_score_multiplier < 1:
            raise ValueError("degraded evidence multiplier must be at least one")
        self._policy_version = policy_version
        self._minimum_fused_score = minimum_fused_score
        self._minimum_score_gap = minimum_score_gap
        self._degraded_score_multiplier = degraded_score_multiplier

    def decide(  # pylint: disable=too-many-arguments
        self,
        *,
        run_id: UUID,
        system_id: UUID,
        retrieval: RetrievalResult,
        decided_at: datetime,
        conflicting_chunk_ids: tuple[UUID, ...] = (),
        required_terms: tuple[str, ...] = (),
    ) -> EvidenceDecision:
        if decided_at.tzinfo is None:
            raise ValueError("evidence decision time must be timezone-aware")
        if any(not math.isfinite(hit.fused_score) for hit in retrieval.hits):
            raise ValueError("evidence fused scores must be finite")
        normalized_query = normalize_question(retrieval.query)
        candidates = tuple(
            EvidenceCandidateSummary(
                chunk_id=hit.chunk_id,
                source_id=hit.source_id,
                source_name=hit.source_name,
                source_version=hit.source_version,
                fused_score=hit.fused_score,
                channels=hit.channels,
            )
            for hit in retrieval.hits
        )
        applied_threshold = self._minimum_fused_score
        if retrieval.degraded_reasons:
            applied_threshold *= self._degraded_score_multiplier

        outcome, reasons = self._evaluate(
            retrieval=retrieval,
            applied_threshold=applied_threshold,
            conflicting_chunk_ids=conflicting_chunk_ids,
            required_terms=required_terms,
        )
        return EvidenceDecision(
            id=uuid4(),
            run_id=run_id,
            system_id=system_id,
            query=retrieval.query,
            normalized_query=normalized_query,
            outcome=outcome,
            reason_codes=reasons,
            score=retrieval.hits[0].fused_score if retrieval.hits else None,
            applied_score_threshold=applied_threshold,
            policy_version=self._policy_version,
            candidates=candidates,
            degraded_reasons=retrieval.degraded_reasons,
            decided_at=decided_at,
        )

    def _evaluate(
        self,
        *,
        retrieval: RetrievalResult,
        applied_threshold: float,
        conflicting_chunk_ids: tuple[UUID, ...],
        required_terms: tuple[str, ...],
    ) -> tuple[EvidenceDecisionOutcome, tuple[EvidenceReasonCode, ...]]:
        hit_ids = {hit.chunk_id for hit in retrieval.hits}
        if any(chunk_id not in hit_ids for chunk_id in conflicting_chunk_ids):
            raise ValueError("conflicting chunks must belong to the retrieval result")
        if conflicting_chunk_ids:
            return (
                EvidenceDecisionOutcome.CONFLICTING,
                (EvidenceReasonCode.CONFLICTING_EVIDENCE,),
            )
        if not retrieval.hits:
            return EvidenceDecisionOutcome.INSUFFICIENT, (EvidenceReasonCode.NO_EVIDENCE,)
        reasons: list[EvidenceReasonCode] = []
        if any(not hit.locators for hit in retrieval.hits):
            reasons.append(EvidenceReasonCode.SOURCE_LOCATION_MISSING)
        if retrieval.hits[0].fused_score < applied_threshold:
            reasons.append(EvidenceReasonCode.SCORE_BELOW_THRESHOLD)
        if len(retrieval.hits) > 1 and self._minimum_score_gap > 0:
            score_gap = retrieval.hits[0].fused_score - retrieval.hits[1].fused_score
            if score_gap < self._minimum_score_gap:
                reasons.append(EvidenceReasonCode.SCORE_GAP_TOO_SMALL)
        normalized_terms = tuple(normalize_question(term) for term in required_terms)
        evidence_text = normalize_question(" ".join(hit.text for hit in retrieval.hits))
        if any(term not in evidence_text for term in normalized_terms):
            reasons.append(EvidenceReasonCode.REQUIRED_TERM_NOT_COVERED)
        if reasons:
            return EvidenceDecisionOutcome.INSUFFICIENT, tuple(reasons)
        return EvidenceDecisionOutcome.SUFFICIENT, ()


def normalize_question(question: str) -> str:
    normalized = unicodedata.normalize("NFKC", question)
    collapsed = " ".join(normalized.split()).casefold()
    if not collapsed:
        raise ValueError("question must not be blank")
    return collapsed
