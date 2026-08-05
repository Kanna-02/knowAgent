from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from knowagent.agent.evaluation import EvaluationObservation, evaluate_phase2


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Phase 2 AC-004/AC-005 gate")
    parser.add_argument("observations", type=Path, help="UTF-8 JSONL observation file")
    args = parser.parse_args()
    try:
        observations = _load_observations(args.observations)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    report = evaluate_phase2(observations)
    print(report.model_dump_json(indent=2))
    return 0 if report.passed else 1


def _load_observations(path: Path) -> tuple[EvaluationObservation, ...]:
    observations: list[EvaluationObservation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            observations.append(EvaluationObservation.model_validate_json(line))
        except (json.JSONDecodeError, ValidationError) as error:
            raise ValueError(f"invalid observation at line {line_number}: {error}") from error
    return tuple(observations)


if __name__ == "__main__":
    raise SystemExit(main())
