from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from knowagent.agent.domain.models import GenerationEvent, GenerationRequest


class LlmProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]: ...
