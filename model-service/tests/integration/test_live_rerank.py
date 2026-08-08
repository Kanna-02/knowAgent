from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowagent_model.app import create_app
from knowagent_model.embedding import EmbeddingBatch
from knowagent_model.flag_embedding import (
    FlagEmbeddingRerankConfig,
    FlagEmbeddingRerankService,
)
from knowagent_model.settings import ModelServiceSettings


class _UnusedEmbeddingService:
    async def embed(self, *, model: str, texts: tuple[str, ...]) -> EmbeddingBatch:
        del model, texts
        raise AssertionError("the live rerank test must not call the embedding provider")

    async def ready(self) -> bool:
        return True


@pytest.mark.integration
def test_live_local_rerank_http_contract() -> None:
    model_path_value = os.getenv("KNOWAGENT_TEST_RERANK_MODEL_PATH", "").strip()
    if not model_path_value:
        pytest.skip("local Rerank model path is not configured")
    model_path = Path(model_path_value)
    if not (model_path / "model.safetensors").is_file():
        pytest.skip("local Rerank model weights are unavailable")

    model = os.getenv("KNOWAGENT_TEST_RERANK_MODEL", "BAAI/bge-reranker-v2-m3").strip()
    model_version = os.getenv(
        "KNOWAGENT_TEST_RERANK_MODEL_VERSION", "BAAI-bge-reranker-v2-m3-local"
    ).strip()
    service = FlagEmbeddingRerankService(
        config=FlagEmbeddingRerankConfig(
            model=model,
            model_path=str(model_path),
            model_version=model_version,
            batch_size=1,
            max_length=256,
            max_concurrency=1,
            use_fp16=False,
            device=os.getenv("KNOWAGENT_TEST_RERANK_DEVICE", "").strip() or None,
        )
    )

    with TestClient(
        create_app(
            service=_UnusedEmbeddingService(),
            rerank_service=service,
            settings=ModelServiceSettings(rerank_model=model, rerank_model_path=str(model_path)),
        )
    ) as client:
        response = client.post(
            "/v1/rerank",
            json={
                "model": model,
                "query": "ESB 服务发布前需要做什么？",
                "documents": [
                    "ESB 服务发布前必须先完成审核。",
                    "员工食堂周五提供面条。",
                ],
                "top_k": 2,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model"] == model
    assert payload["model_version"] == model_version
    assert [item["index"] for item in payload["results"]] == [0, 1]
    assert payload["results"][0]["score"] > payload["results"][1]["score"]
