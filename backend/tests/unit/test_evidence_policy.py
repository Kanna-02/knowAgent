from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from knowagent.agent.application.evidence_decision import (
    DeterministicEvidencePolicy,
    normalize_question,
)
from knowagent.agent.domain.models import EvidenceDecisionOutcome, EvidenceReasonCode
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.domain.models import FusedSearchHit, RetrievalResult, SearchHit

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def make_hit(*, fused_score: float = 0.02, text: str = "发布前执行数据库迁移。") -> FusedSearchHit:
    raw = SearchHit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text=text,
        locators=(
            SourceLocator(
                document_id=uuid4(),
                document_version_id=uuid4(),
                source_type=SourceType.PDF,
                block_index=0,
                page_number=3,
            ),
        ),
        source_name="部署手册.pdf",
        source_version="2",
        score=0.9,
    )
    return FusedSearchHit.from_search_hit(
        raw,
        fused_score=fused_score,
        channels=("keyword", "vector"),
    )


def policy() -> DeterministicEvidencePolicy:
    return DeterministicEvidencePolicy(
        policy_version="evidence-v1",
        minimum_fused_score=0.015,
        minimum_score_gap=0.001,
        degraded_score_multiplier=1.2,
    )


def decide(
    retrieval: RetrievalResult,
    *,
    conflicting_chunk_ids: tuple = (),
    required_terms: tuple[str, ...] = (),
):
    return policy().decide(
        run_id=uuid4(),
        system_id=uuid4(),
        retrieval=retrieval,
        decided_at=NOW,
        conflicting_chunk_ids=conflicting_chunk_ids,
        required_terms=required_terms,
    )


def test_decide_with_grounded_candidate_returns_sufficient_decision() -> None:
    hit = make_hit()

    decision = decide(RetrievalResult(query="如何发布？", hits=(hit,)))

    assert decision.outcome is EvidenceDecisionOutcome.SUFFICIENT
    assert decision.reason_codes == ()
    assert decision.score == hit.fused_score
    assert decision.candidates[0].chunk_id == hit.chunk_id
    assert decision.policy_version == "evidence-v1"


def test_decide_without_candidates_records_no_evidence_reason() -> None:
    decision = decide(RetrievalResult(query="未知问题", hits=()))

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.NO_EVIDENCE,)
    assert decision.score is None


def test_decide_with_low_score_records_threshold_reason() -> None:
    decision = decide(RetrievalResult(query="如何发布？", hits=(make_hit(fused_score=0.01),)))

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.SCORE_BELOW_THRESHOLD,)
    assert decision.applied_score_threshold == 0.015


def test_decide_with_missing_locator_records_unverifiable_source_reason() -> None:
    hit = replace(make_hit(), locators=())

    decision = decide(RetrievalResult(query="如何发布？", hits=(hit,)))

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.SOURCE_LOCATION_MISSING,)


def test_decide_with_explicit_conflict_records_conflicting_outcome() -> None:
    first = make_hit(text="超时配置为 10 秒。")
    second = make_hit(fused_score=0.018, text="超时配置为 30 秒。")

    decision = decide(
        RetrievalResult(query="超时配置是多少？", hits=(first, second)),
        conflicting_chunk_ids=(first.chunk_id, second.chunk_id),
    )

    assert decision.outcome is EvidenceDecisionOutcome.CONFLICTING
    assert decision.reason_codes == (EvidenceReasonCode.CONFLICTING_EVIDENCE,)


def test_decide_when_vector_degraded_applies_stricter_score_threshold() -> None:
    decision = decide(
        RetrievalResult(
            query="如何发布？",
            hits=(make_hit(fused_score=0.017),),
            degraded_reasons=("VECTOR_UNAVAILABLE",),
        )
    )

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.SCORE_BELOW_THRESHOLD,)
    assert decision.applied_score_threshold == 0.018


def test_decide_with_indistinguishable_top_candidates_records_score_gap_reason() -> None:
    first = make_hit(fused_score=0.02)
    second = make_hit(fused_score=0.0195)

    decision = decide(RetrievalResult(query="如何发布？", hits=(first, second)))

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.SCORE_GAP_TOO_SMALL,)


def test_decide_when_required_term_is_not_covered_records_coverage_reason() -> None:
    decision = decide(
        RetrievalResult(query="ESB TLS 如何配置？", hits=(make_hit(text="ESB 发布步骤。"),)),
        required_terms=("TLS",),
    )

    assert decision.outcome is EvidenceDecisionOutcome.INSUFFICIENT
    assert decision.reason_codes == (EvidenceReasonCode.REQUIRED_TERM_NOT_COVERED,)


def test_decide_with_multiple_failed_gates_records_all_deterministic_reasons() -> None:
    hit = replace(make_hit(fused_score=0.01), locators=())

    decision = decide(
        RetrievalResult(query="ESB TLS 如何配置？", hits=(hit,)),
        required_terms=("TLS",),
    )

    assert decision.reason_codes == (
        EvidenceReasonCode.SOURCE_LOCATION_MISSING,
        EvidenceReasonCode.SCORE_BELOW_THRESHOLD,
        EvidenceReasonCode.REQUIRED_TERM_NOT_COVERED,
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"policy_version": " "}, "version"),
        ({"minimum_fused_score": -0.1}, "thresholds"),
        ({"minimum_fused_score": float("nan")}, "finite"),
        ({"minimum_score_gap": float("inf")}, "finite"),
        ({"degraded_score_multiplier": 0.9}, "multiplier"),
        ({"degraded_score_multiplier": float("nan")}, "finite"),
    ],
)
def test_policy_with_invalid_configuration_raises_value_error(
    overrides: dict[str, str | float],
    message: str,
) -> None:
    arguments: dict[str, str | float] = {
        "policy_version": "evidence-v1",
        "minimum_fused_score": 0.015,
        "minimum_score_gap": 0.001,
        "degraded_score_multiplier": 1.2,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        DeterministicEvidencePolicy(**arguments)  # type: ignore[arg-type]


def test_decide_with_naive_timestamp_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        policy().decide(
            run_id=uuid4(),
            system_id=uuid4(),
            retrieval=RetrievalResult(query="如何发布？", hits=(make_hit(),)),
            decided_at=NOW.replace(tzinfo=None),
        )


def test_decide_with_conflict_outside_retrieval_result_raises_value_error() -> None:
    with pytest.raises(ValueError, match="must belong"):
        decide(
            RetrievalResult(query="如何发布？", hits=(make_hit(),)),
            conflicting_chunk_ids=(uuid4(),),
        )


def test_decide_with_covered_normalized_term_remains_sufficient() -> None:
    decision = decide(
        RetrievalResult(query="ESB TLS 如何配置？", hits=(make_hit(text="ESB TLS 发布步骤。"),)),
        required_terms=("ＴＬＳ",),
    )

    assert decision.outcome is EvidenceDecisionOutcome.SUFFICIENT


def test_decide_normalizes_evidence_text_before_required_term_matching() -> None:
    decision = decide(
        RetrievalResult(
            query="ESB TLS 如何配置？", hits=(make_hit(text="ESB ＴＬＳ\n 发布步骤。"),)
        ),
        required_terms=("TLS 发布",),
    )

    assert decision.outcome is EvidenceDecisionOutcome.SUFFICIENT


def test_decide_with_non_finite_fused_score_raises_value_error() -> None:
    with pytest.raises(ValueError, match="finite"):
        decide(RetrievalResult(query="如何发布？", hits=(make_hit(fused_score=float("nan")),)))


def test_normalize_question_with_blank_input_raises_value_error() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_question(" \t\n")
