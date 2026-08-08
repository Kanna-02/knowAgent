from __future__ import annotations

from types import SimpleNamespace

import pytest

from knowagent_model.flag_embedding import (
    FlagEmbeddingRerankConfig,
    FlagEmbeddingRerankService,
)
from knowagent_model.rerank import RerankServiceError


class StubRunner:
    def __init__(self, scores: object) -> None:
        self.scores = scores
        self.calls: list[tuple[list[tuple[str, str]], int, int, bool]] = []

    def compute_score(
        self,
        sentence_pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        max_length: int,
        normalize: bool,
    ) -> object:
        self.calls.append((sentence_pairs, batch_size, max_length, normalize))
        return self.scores


@pytest.mark.anyio
async def test_rerank_sorts_scores_and_returns_original_indexes() -> None:
    runner = StubRunner([0.2, 0.9, -0.1])
    service = FlagEmbeddingRerankService(
        config=FlagEmbeddingRerankConfig(
            model="BAAI/bge-reranker-v2-m3",
            model_version="revision-1",
            batch_size=2,
            max_length=512,
            max_concurrency=1,
            use_fp16=False,
        ),
        runner_factory=lambda config: runner,
    )

    result = await service.rerank(
        model="BAAI/bge-reranker-v2-m3",
        query="如何部署？",
        documents=("文档甲", "文档乙", "文档丙"),
        top_k=2,
    )

    assert [(item.index, item.score) for item in result.results] == [(1, 0.9), (0, 0.2)]
    assert runner.calls == [
        (
            [("如何部署？", "文档甲"), ("如何部署？", "文档乙"), ("如何部署？", "文档丙")],
            2,
            512,
            False,
        )
    ]
    assert await service.ready() is True


@pytest.mark.anyio
@pytest.mark.parametrize("scores", [[0.2], [0.2, float("nan")], "invalid"])
async def test_rerank_maps_invalid_model_output_to_sanitized_error(scores: object) -> None:
    service = FlagEmbeddingRerankService(
        config=FlagEmbeddingRerankConfig(
            model="BAAI/bge-reranker-v2-m3",
            model_version="revision-1",
            batch_size=2,
            max_length=512,
            max_concurrency=1,
            use_fp16=False,
        ),
        runner_factory=lambda config: StubRunner(scores),
    )

    with pytest.raises(RerankServiceError, match="unavailable"):
        await service.rerank(
            model="BAAI/bge-reranker-v2-m3",
            query="问题",
            documents=("甲", "乙"),
            top_k=2,
        )


@pytest.mark.anyio
async def test_rerank_rejects_model_mismatch_without_loading_runner() -> None:
    loaded = False

    def factory(config: FlagEmbeddingRerankConfig) -> StubRunner:
        del config
        nonlocal loaded
        loaded = True
        return StubRunner([0.1])

    service = FlagEmbeddingRerankService(
        config=FlagEmbeddingRerankConfig(
            model="BAAI/bge-reranker-v2-m3",
            model_version="revision-1",
            batch_size=2,
            max_length=512,
            max_concurrency=1,
            use_fp16=False,
        ),
        runner_factory=factory,
    )

    with pytest.raises(RerankServiceError, match="not configured"):
        await service.rerank(
            model="other-model",
            query="问题",
            documents=("文档",),
            top_k=1,
        )

    assert loaded is False


@pytest.mark.anyio
async def test_rerank_keeps_external_model_id_when_loading_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_models: list[str] = []

    class LocalRunner(StubRunner):
        def __init__(self, model: str, **kwargs: object) -> None:
            del kwargs
            loaded_models.append(model)
            super().__init__([0.8, 0.1])

    monkeypatch.setattr(
        "knowagent_model.flag_embedding.importlib.import_module",
        lambda name: SimpleNamespace(FlagReranker=LocalRunner),
    )
    service = FlagEmbeddingRerankService(
        config=FlagEmbeddingRerankConfig(
            model="BAAI/bge-reranker-v2-m3",
            model_path="/models/bge-reranker-v2-m3",
            model_version="revision-1",
            batch_size=2,
            max_length=512,
            max_concurrency=1,
            use_fp16=False,
        )
    )

    result = await service.rerank(
        model="BAAI/bge-reranker-v2-m3",
        query="问题",
        documents=("相关文档", "无关文档"),
        top_k=1,
    )

    assert loaded_models == ["/models/bge-reranker-v2-m3"]
    assert result.model == "BAAI/bge-reranker-v2-m3"
