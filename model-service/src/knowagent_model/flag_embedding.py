from __future__ import annotations

import asyncio
import importlib
import logging
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, cast

from knowagent_model.rerank import RerankBatch, RerankResult, RerankServiceError

LOGGER = logging.getLogger(__name__)


class RerankRunner(Protocol):  # pylint: disable=too-few-public-methods
    def compute_score(
        self,
        sentence_pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        max_length: int,
        normalize: bool,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class FlagEmbeddingRerankConfig:  # pylint: disable=too-many-instance-attributes
    model: str
    model_version: str
    batch_size: int
    max_length: int
    max_concurrency: int
    use_fp16: bool
    device: str | None = None
    model_path: str | None = None

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.model_version.strip():
            raise ValueError("rerank model metadata must not be blank")
        if any(value <= 0 for value in (self.batch_size, self.max_length, self.max_concurrency)):
            raise ValueError("rerank runtime limits must be positive")
        if self.device is not None and not self.device.strip():
            raise ValueError("rerank device must be omitted or non-blank")
        if self.model_path is not None and not self.model_path.strip():
            raise ValueError("rerank model path must be omitted or non-blank")


RunnerFactory = Callable[[FlagEmbeddingRerankConfig], RerankRunner]


class FlagEmbeddingRerankService:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        *,
        config: FlagEmbeddingRerankConfig,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        self._config = config
        self._runner_factory = runner_factory or _create_runner
        self._runner: RerankRunner | None = None
        self._load_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(config.max_concurrency)

    async def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: tuple[str, ...],
        top_k: int,
    ) -> RerankBatch:
        if model != self._config.model:
            raise RerankServiceError(
                code="RERANK_MODEL_NOT_CONFIGURED",
                message="Requested rerank model is not configured",
                status_code=422,
            )
        if not query.strip() or not documents or any(not item.strip() for item in documents):
            raise RerankServiceError(
                code="RERANK_INPUT_INVALID",
                message="Rerank query and documents must not be blank",
                status_code=422,
            )
        if top_k <= 0 or top_k > len(documents):
            raise RerankServiceError(
                code="RERANK_TOP_K_INVALID",
                message="Rerank top_k exceeds the candidate count",
                status_code=422,
            )

        started = time.perf_counter()
        runner = await self._get_runner()
        pairs = [(query.strip(), document.strip()) for document in documents]
        async with self._semaphore:
            try:
                raw_scores = await asyncio.to_thread(
                    runner.compute_score,
                    pairs,
                    batch_size=self._config.batch_size,
                    max_length=self._config.max_length,
                    normalize=False,
                )
                scores = _normalize_scores(raw_scores, expected_count=len(documents))
            except RerankServiceError:
                raise
            except Exception as error:
                raise _unavailable() from error

        ranked = sorted(enumerate(scores), key=lambda item: (-item[1], item[0]))[:top_k]
        LOGGER.info(
            "rerank inference completed",
            extra={
                "model": self._config.model,
                "model_version": self._config.model_version,
                "candidate_count": len(documents),
                "result_count": len(ranked),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return RerankBatch(
            model=self._config.model,
            model_version=self._config.model_version,
            results=tuple(RerankResult(index=index, score=score) for index, score in ranked),
        )

    async def ready(self) -> bool:
        try:
            await self._get_runner()
        except RerankServiceError:
            return False
        return True

    async def _get_runner(self) -> RerankRunner:
        if self._runner is not None:
            return self._runner
        async with self._load_lock:
            if self._runner is not None:
                return self._runner
            try:
                self._runner = await asyncio.to_thread(self._runner_factory, self._config)
            except Exception as error:
                LOGGER.warning(
                    "rerank model load failed",
                    extra={
                        "model": self._config.model,
                        "model_version": self._config.model_version,
                        "error_type": type(error).__name__,
                    },
                )
                raise _unavailable() from error
            return self._runner


def _create_runner(config: FlagEmbeddingRerankConfig) -> RerankRunner:
    try:
        module = importlib.import_module("FlagEmbedding")
        runner_type = getattr(module, "FlagReranker")
    except (ImportError, AttributeError) as error:
        raise _unavailable() from error
    if not callable(runner_type):
        raise _unavailable()
    devices = config.device if config.device is not None else None
    runner = runner_type(
        config.model_path or config.model,
        use_fp16=config.use_fp16,
        trust_remote_code=False,
        devices=devices,
        batch_size=config.batch_size,
        max_length=config.max_length,
        normalize=False,
    )
    return cast(RerankRunner, runner)


def _normalize_scores(raw_scores: object, *, expected_count: int) -> tuple[float, ...]:
    if isinstance(raw_scores, (bool, str, bytes)):
        raise _unavailable()
    if isinstance(raw_scores, (int, float)):
        values: list[object] = [raw_scores]
    elif isinstance(raw_scores, Iterable):
        values = list(raw_scores)
    else:
        raise _unavailable()
    if len(values) != expected_count:
        raise _unavailable()
    normalized: list[float] = []
    for value in values:
        if isinstance(value, (bool, str, bytes)):
            raise _unavailable()
        try:
            score = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError) as error:
            raise _unavailable() from error
        if not math.isfinite(score):
            raise _unavailable()
        normalized.append(score)
    return tuple(normalized)


def _unavailable() -> RerankServiceError:
    return RerankServiceError(
        code="RERANK_UNAVAILABLE",
        message="Rerank service is unavailable",
        status_code=503,
    )
