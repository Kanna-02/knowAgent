from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingBatch:
    model: str
    model_version: str
    dimension: int
    normalized: bool
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class EmbeddingService(Protocol):
    async def embed(self, *, model: str, texts: tuple[str, ...]) -> EmbeddingBatch: ...

    async def ready(self) -> bool: ...
