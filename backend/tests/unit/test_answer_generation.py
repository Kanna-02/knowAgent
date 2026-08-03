from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from knowagent.agent.application.answer_generation import AnswerGenerator
from knowagent.agent.domain.models import GenerationEvent, GenerationRequest
from knowagent.agent.infrastructure.openai_compatible import OpenAiCompatibleLlmProvider
from knowagent.agent.prompts import load_prompt_definition
from knowagent.common.errors import ProviderUnavailableError, ValidationError
from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.domain.models import EvidenceBundle, EvidenceItem


def evidence_bundle() -> EvidenceBundle:
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


class StubLlmProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    @property
    def model(self) -> str:
        return "qwen-test"

    @property
    def prompt_version(self) -> str:
        return "grounded-answer-v1"

    async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
        assert request.question == "发布前要做什么？"
        content = json.dumps(self.payload, ensure_ascii=False)
        midpoint = len(content) // 2
        yield GenerationEvent.delta(content[:midpoint])
        yield GenerationEvent.delta(content[midpoint:])
        yield GenerationEvent.completed()


@pytest.mark.asyncio
async def test_generate_returns_verified_answer_and_immutable_citation_snapshot() -> None:
    provider = StubLlmProvider(
        {
            "claims": [
                {
                    "text": "发布前必须执行数据库迁移。",
                    "citations": [{"evidence_id": "E1", "quote": "发布前必须执行数据库迁移。"}],
                }
            ],
        }
    )

    answer = await AnswerGenerator(provider).generate(
        question="发布前要做什么？", evidence=evidence_bundle()
    )

    assert answer.text == "发布前必须执行数据库迁移。"
    assert answer.citations[0].rank == 1
    assert answer.citations[0].claim_rank == 1
    assert answer.citations[0].source_name == "部署手册.md"
    assert answer.citations[0].quoted_text == "发布前必须执行数据库迁移。"
    assert answer.citations[0].locators[0].line_start == 8
    assert answer.model == "qwen-test"
    assert answer.prompt_version == "grounded-answer-v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "citations",
    [
        [{"evidence_id": "E9", "quote": "发布前必须执行数据库迁移。"}],
        [{"evidence_id": "E1", "quote": "这段话不在证据中"}],
        [],
    ],
)
async def test_generate_rejects_unknown_fabricated_or_missing_citations(
    citations: list[dict[str, str]],
) -> None:
    provider = StubLlmProvider(
        {
            "claims": [
                {
                    "text": "发布前必须执行数据库迁移。",
                    "citations": citations,
                }
            ]
        }
    )

    with pytest.raises(ValidationError, match="引用"):
        await AnswerGenerator(provider).generate(
            question="发布前要做什么？", evidence=evidence_bundle()
        )


@pytest.mark.asyncio
async def test_generate_rejects_claim_not_covered_by_quoted_evidence() -> None:
    provider = StubLlmProvider(
        {
            "claims": [
                {
                    "text": "生产密码是 123456。",
                    "citations": [{"evidence_id": "E1", "quote": "。"}],
                }
            ]
        }
    )

    with pytest.raises(ValidationError, match="支撑"):
        await AnswerGenerator(provider).generate(
            question="发布前要做什么？", evidence=evidence_bundle()
        )


def test_grounded_answer_prompt_loads_versioned_operational_metadata() -> None:
    prompt = load_prompt_definition("grounded-answer-v1")

    assert prompt.scenario == "grounded_answer"
    assert prompt.version == "grounded-answer-v1"
    assert prompt.enabled is True
    assert prompt.created_at.isoformat() == "2026-08-03T00:00:00+00:00"
    assert prompt.change_note
    assert '"claims"' in prompt.content


def test_grounded_answer_prompt_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="unknown prompt version"):
        load_prompt_definition("grounded-answer-v999")


@pytest.mark.asyncio
async def test_generate_rejects_blank_claim_after_normalization() -> None:
    provider = StubLlmProvider(
        {
            "claims": [
                {
                    "text": "   ",
                    "citations": [{"evidence_id": "E1", "quote": "发布前必须执行数据库迁移。"}],
                }
            ]
        }
    )

    with pytest.raises(ValidationError, match="声明不能为空"):
        await AnswerGenerator(provider).generate(
            question="发布前要做什么？", evidence=evidence_bundle()
        )


@pytest.mark.asyncio
async def test_openai_provider_emits_all_delta_and_completed_events() -> None:
    lines = [
        'data: {"choices":[{"delta":{"content":"{\\"answer\\":"}}]}',
        'data: {"choices":[{"delta":{"content":"\\"ok\\"}"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://dashscope.example/compatible-mode/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "qwen3.6-plus"
        assert body["stream"] is True
        return httpx.Response(200, text="\n\n".join(lines))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/compatible-mode/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=load_prompt_definition("grounded-answer-v1"),
            client=client,
        )
        events = [
            event
            async for event in provider.generate(
                request=GenerationRequest(
                    question="发布前要做什么？",
                    evidence=evidence_bundle(),
                )
            )
        ]

    assert [event.kind for event in events] == ["delta", "delta", "completed"]
    assert "".join(event.text for event in events) == '{"answer":"ok"}'


@pytest.mark.asyncio
async def test_openai_provider_accepts_stop_reason_when_done_sentinel_is_omitted() -> None:
    line = 'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}]}'

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text=line)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/compatible-mode/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=load_prompt_definition("grounded-answer-v1"),
            client=client,
        )
        events = [
            event
            async for event in provider.generate(
                request=GenerationRequest(
                    question="发布前要做什么？",
                    evidence=evidence_bundle(),
                )
            )
        ]

    assert [event.kind for event in events] == ["delta", "completed"]
    assert provider.model == "qwen3.6-plus"
    assert provider.prompt_version == "grounded-answer-v1"


def test_openai_provider_rejects_invalid_configuration() -> None:
    prompt = load_prompt_definition("grounded-answer-v1")

    with pytest.raises(ValueError, match="configuration"):
        OpenAiCompatibleLlmProvider(
            base_url="",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=prompt,
        )
    with pytest.raises(ValueError, match="timeout"):
        OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=0,
            prompt=prompt,
        )
    with pytest.raises(ValueError, match="enabled"):
        OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=replace(prompt, enabled=False),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lines",
    [
        [
            'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"length"}]}',
            "data: [DONE]",
        ],
        ['data: {"choices":[{"delta":{"content":"{}"}}]}', "data: [DONE]"],
    ],
)
async def test_openai_provider_rejects_non_successful_or_unconfirmed_completion(
    lines: list[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text="\n\n".join(lines))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/compatible-mode/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=load_prompt_definition("grounded-answer-v1"),
            client=client,
        )
        with pytest.raises(ProviderUnavailableError):
            _ = [
                event
                async for event in provider.generate(
                    request=GenerationRequest(
                        question="发布前要做什么？",
                        evidence=evidence_bundle(),
                    )
                )
            ]


@pytest.mark.asyncio
async def test_openai_provider_maps_http_failures_without_exposing_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, text='{"message":"secret upstream detail"}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAiCompatibleLlmProvider(
            base_url="https://dashscope.example/compatible-mode/v1",
            api_key="secret",
            model="qwen3.6-plus",
            timeout_seconds=30,
            prompt=load_prompt_definition("grounded-answer-v1"),
            client=client,
        )
        with pytest.raises(ProviderUnavailableError) as captured:
            _ = [
                event
                async for event in provider.generate(
                    request=GenerationRequest(
                        question="发布前要做什么？",
                        evidence=evidence_bundle(),
                    )
                )
            ]

    assert "secret upstream detail" not in str(captured.value)
