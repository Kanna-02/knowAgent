from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from knowagent.agent.application.answer_generation import (
    AnswerGenerator,
    StreamedAnswerCompleted,
    StreamedAnswerDelta,
)
from knowagent.agent.domain.models import GenerationEvent, GenerationRequest
from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.domain.models import EvidenceBundle, EvidenceItem


def _evidence_bundle() -> EvidenceBundle:
    item = EvidenceItem(
        evidence_id="E1",
        chunk_id=uuid4(),
        source_id=uuid4(),
        quoted_text="发布前必须执行数据库迁移。",
        source_name="部署手册.md",
        source_version="2",
        locators=(
            SourceLocator(
                document_id=uuid4(),
                document_version_id=uuid4(),
                source_type=SourceType.MARKDOWN,
                block_index=0,
                heading_path=("发布",),
                paragraph_start=1,
                paragraph_end=1,
                line_start=8,
                line_end=8,
            ),
        ),
    )
    return EvidenceBundle(items=(item,), prompt_text="[E1]\n发布前必须执行数据库迁移。")


class _StubLlm:
    def __init__(self, payload: dict[str, object], *, chunks: int = 2) -> None:
        self.payload = payload
        self.chunks = chunks

    @property
    def model(self) -> str:
        return "qwen-test"

    @property
    def prompt_version(self) -> str:
        return "grounded-answer-v1"

    async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
        assert request.question == "发布前要做什么？"
        content = json.dumps(self.payload, ensure_ascii=False)
        step = max(1, len(content) // self.chunks)
        parts = [content[i : i + step] for i in range(0, len(content), step)]
        for part in parts:
            yield GenerationEvent.delta(part)
        yield GenerationEvent.completed()


async def _collect(stream):
    return [item async for item in stream]


@pytest.mark.anyio
async def test_generate_stream_returns_deltas_and_verified_answer() -> None:
    provider = _StubLlm(
        {
            "claims": [
                {
                    "text": "发布前必须执行数据库迁移。",
                    "citations": [{"evidence_id": "E1", "quote": "发布前必须执行数据库迁移。"}],
                }
            ],
        }
    )
    streamed = await _collect(
        AnswerGenerator(provider).generate_stream(
            question="发布前要做什么？", evidence=_evidence_bundle()
        )
    )
    deltas = [event.text for event in streamed if isinstance(event, StreamedAnswerDelta)]
    completed = [event for event in streamed if isinstance(event, StreamedAnswerCompleted)]
    assert deltas == ["发布前必须执行数据库迁移。"]
    assert len(completed) == 1
    assert completed[0].answer.text == "发布前必须执行数据库迁移。"
    assert completed[0].answer.citations[0].source_name == "部署手册.md"


@pytest.mark.anyio
async def test_generate_stream_yields_verified_claim_before_provider_completes() -> None:
    first_claim_sent = asyncio.Event()
    allow_completion = asyncio.Event()

    class _PausedLlm:
        model = "qwen-test"
        prompt_version = "grounded-answer-v1"

        async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
            del request
            first_claim_sent.set()
            yield GenerationEvent.delta(
                '{"claims":[{"text":"发布前必须执行数据库迁移。",'
                '"citations":[{"evidence_id":"E1","quote":"发布前必须执行数据库迁移。"}]}'
            )
            await allow_completion.wait()
            yield GenerationEvent.delta("]}")
            yield GenerationEvent.completed()

    stream = AnswerGenerator(_PausedLlm()).generate_stream(
        question="发布前要做什么？", evidence=_evidence_bundle()
    )
    pending = asyncio.create_task(anext(stream))
    await first_claim_sent.wait()
    first = await asyncio.wait_for(pending, timeout=0.2)

    assert isinstance(first, StreamedAnswerDelta)
    assert first.text == "发布前必须执行数据库迁移。"

    allow_completion.set()
    remaining = [event async for event in stream]
    assert len(remaining) == 1
    assert isinstance(remaining[0], StreamedAnswerCompleted)


@pytest.mark.anyio
async def test_generate_stream_empty_evidence_raises() -> None:
    empty = EvidenceBundle(items=(), prompt_text="")
    with pytest.raises(ValidationError):
        await _collect(AnswerGenerator(_StubLlm({})).generate_stream(question="x", evidence=empty))


@pytest.mark.anyio
async def test_generate_stream_unsupported_citation_raises_validation() -> None:
    provider = _StubLlm(
        {
            "claims": [
                {
                    "text": "不存在于证据中的内容",
                    "citations": [{"evidence_id": "E1", "quote": "不存在于证据中的内容"}],
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        await _collect(
            AnswerGenerator(provider).generate_stream(
                question="发布前要做什么？", evidence=_evidence_bundle()
            )
        )


@pytest.mark.anyio
async def test_generate_stream_missing_completion_raises_provider_error() -> None:
    class _NoCompletion:
        model = "qwen-test"
        prompt_version = "grounded-answer-v1"

        async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
            yield GenerationEvent.delta(json.dumps({"claims": []}, ensure_ascii=False))

    with pytest.raises(ProviderUnavailableError):
        await _collect(
            AnswerGenerator(_NoCompletion()).generate_stream(
                question="发布前要做什么？", evidence=_evidence_bundle()
            )
        )
