from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvaluationOutcome = Literal["answered", "refused", "error"]


class EvaluationObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1, max_length=200)
    expected_outcome: Literal["answered", "refused"]
    actual_outcome: EvaluationOutcome
    real_esb_question: bool
    answer_correct: bool | None
    citations_supported: bool | None
    ticket_id: str | None


class Phase2EvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    total_cases: int
    real_answerable_cases: int
    unanswerable_cases: int
    answer_accuracy: float
    citation_support_rate: float
    refusal_recall: float
    refusals_without_ticket: int
    ungrounded_answers: int
    duplicate_case_ids: int
    failure_reasons: tuple[str, ...]


def evaluate_phase2(
    observations: tuple[EvaluationObservation, ...],
) -> Phase2EvaluationReport:
    answerable = tuple(item for item in observations if item.expected_outcome == "answered")
    real_answerable = tuple(item for item in answerable if item.real_esb_question)
    unanswerable = tuple(item for item in observations if item.expected_outcome == "refused")

    answer_accuracy = _ratio(
        sum(
            item.actual_outcome == "answered" and item.answer_correct is True
            for item in real_answerable
        ),
        len(real_answerable),
    )
    citation_support_rate = _ratio(
        sum(
            item.actual_outcome == "answered" and item.citations_supported is True
            for item in real_answerable
        ),
        len(real_answerable),
    )
    refusal_recall = _ratio(
        sum(item.actual_outcome == "refused" for item in unanswerable),
        len(unanswerable),
    )
    refusals_without_ticket = sum(
        item.actual_outcome == "refused" and not item.ticket_id for item in observations
    )
    ungrounded_answers = sum(
        item.expected_outcome == "refused" and item.actual_outcome == "answered"
        for item in observations
    )
    duplicate_case_ids = len(observations) - len({item.case_id for item in observations})

    failures: list[str] = []
    if duplicate_case_ids:
        failures.append("DUPLICATE_CASE_IDS")
    if len(real_answerable) < 50:
        failures.append("ANSWERABLE_CASES_BELOW_50")
    if not unanswerable:
        failures.append("UNANSWERABLE_CASES_MISSING")
    if answer_accuracy < 0.8:
        failures.append("ANSWER_ACCURACY_BELOW_80_PERCENT")
    if citation_support_rate < 0.95:
        failures.append("CITATION_SUPPORT_BELOW_95_PERCENT")
    if refusal_recall < 0.9:
        failures.append("REFUSAL_RECALL_BELOW_90_PERCENT")
    if refusals_without_ticket:
        failures.append("REFUSAL_WITHOUT_TICKET")
    if ungrounded_answers:
        failures.append("UNGROUNDED_ANSWER_RETURNED")

    return Phase2EvaluationReport(
        passed=not failures,
        total_cases=len(observations),
        real_answerable_cases=len(real_answerable),
        unanswerable_cases=len(unanswerable),
        answer_accuracy=answer_accuracy,
        citation_support_rate=citation_support_rate,
        refusal_recall=refusal_recall,
        refusals_without_ticket=refusals_without_ticket,
        ungrounded_answers=ungrounded_answers,
        duplicate_case_ids=duplicate_case_ids,
        failure_reasons=tuple(failures),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
