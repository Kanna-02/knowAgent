from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


@dataclass(frozen=True, slots=True)
class RerankBatch:
    model: str
    model_version: str
    results: tuple[RerankResult, ...]


class RerankServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RerankService(Protocol):
    async def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch: ...

    async def ready(self) -> bool: ...
