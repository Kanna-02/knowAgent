from __future__ import annotations

from pathlib import Path

import pytest

from knowagent.agent.evaluation import EvaluationObservation, evaluate_phase2
from knowagent.agent.evaluation_cli import _load_observations


def _answerable(index: int, *, correct: bool = True, supported: bool = True):
    return EvaluationObservation(
        case_id=f"answerable-{index}",
        expected_outcome="answered",
        actual_outcome="answered",
        real_esb_question=True,
        answer_correct=correct,
        citations_supported=supported,
        ticket_id=None,
    )


def _unanswerable(index: int, *, outcome: str = "refused", ticket: bool = True):
    return EvaluationObservation(
        case_id=f"unanswerable-{index}",
        expected_outcome="refused",
        actual_outcome=outcome,
        real_esb_question=True,
        answer_correct=None,
        citations_supported=None,
        ticket_id=f"ticket-{index}" if ticket else None,
    )


def test_evaluate_phase2_passes_all_quality_thresholds() -> None:
    observations = tuple(_answerable(index) for index in range(50)) + tuple(
        _unanswerable(index) for index in range(10)
    )

    report = evaluate_phase2(observations)

    assert report.passed is True
    assert report.answer_accuracy == 1.0
    assert report.citation_support_rate == 1.0
    assert report.refusal_recall == 1.0
    assert report.refusals_without_ticket == 0
    assert report.ungrounded_answers == 0


def test_evaluate_phase2_fails_without_fifty_real_answerable_cases() -> None:
    report = evaluate_phase2(tuple(_answerable(index) for index in range(49)))

    assert report.passed is False
    assert "ANSWERABLE_CASES_BELOW_50" in report.failure_reasons
    assert "UNANSWERABLE_CASES_MISSING" in report.failure_reasons


def test_evaluate_phase2_reports_threshold_and_safety_failures() -> None:
    observations = (
        tuple(_answerable(index, correct=index < 39, supported=index < 47) for index in range(50))
        + tuple(
            _unanswerable(index, outcome="refused" if index < 8 else "error") for index in range(9)
        )
        + (_unanswerable(9, outcome="answered"),)
        + (_unanswerable(10, ticket=False),)
    )

    report = evaluate_phase2(observations)

    assert report.passed is False
    assert report.answer_accuracy == 0.78
    assert report.citation_support_rate == 0.94
    assert report.refusal_recall < 0.9
    assert report.refusals_without_ticket == 1
    assert report.ungrounded_answers == 1
    assert set(report.failure_reasons) >= {
        "ANSWER_ACCURACY_BELOW_80_PERCENT",
        "CITATION_SUPPORT_BELOW_95_PERCENT",
        "REFUSAL_RECALL_BELOW_90_PERCENT",
        "REFUSAL_WITHOUT_TICKET",
        "UNGROUNDED_ANSWER_RETURNED",
    }


def test_evaluate_phase2_rejects_duplicate_case_ids() -> None:
    observations = tuple(_answerable(0) for _ in range(50)) + tuple(
        _unanswerable(index) for index in range(10)
    )

    report = evaluate_phase2(observations)

    assert report.passed is False
    assert report.duplicate_case_ids == 49
    assert "DUPLICATE_CASE_IDS" in report.failure_reasons


def test_load_observations_reports_invalid_line(tmp_path: Path) -> None:
    observations = tmp_path / "observations.jsonl"
    observations.write_text('{"case_id":', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid observation at line 1"):
        _load_observations(observations)
