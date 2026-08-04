from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from knowagent.agent.domain.models import AnswerSnapshot, GenerationEvent, GenerationRequest


class LlmProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]: ...


class AnswerSnapshotRepository(Protocol):
    def add_or_get(self, snapshot: AnswerSnapshot) -> AnswerSnapshot: ...

    def get_by_run(self, *, system_id: UUID, run_id: UUID) -> AnswerSnapshot | None: ...
