from __future__ import annotations

import pytest

from knowagent.agent.application.query_rewriter import QueryRewriter
from knowagent.agent.domain.conversation import (
    ConversationMessageRole,
    IntentKind,
    QueryRewriteTurn,
)


def turn(
    content: str,
    role: ConversationMessageRole = ConversationMessageRole.USER,
) -> QueryRewriteTurn:
    return QueryRewriteTurn(role=role, content=content)


class StubRewriteLlm:
    """Minimal LLM stub that returns a canned rewrite or raises."""

    def __init__(self, result: str | Exception) -> None:
        self._result = result
        self.calls = 0

    @property
    def rewrite_prompt_version(self) -> str:
        return "query-rewrite-v1"

    async def rewrite_query(
        self,
        *,
        question: str,
        history_turns: tuple[QueryRewriteTurn, ...],
    ) -> str:
        del question, history_turns
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.mark.anyio
async def test_standalone_question_skips_llm() -> None:
    llm = StubRewriteLlm(result="不该被调用")
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="什么是 ESB 总线？",
        history_turns=(turn("上次问了什么"),),
    )
    assert result.intent is IntentKind.STANDALONE
    assert result.rewritten_query == "什么是 ESB 总线？"
    assert llm.calls == 0


@pytest.mark.anyio
async def test_no_history_treated_as_standalone() -> None:
    llm = StubRewriteLlm(result="不该被调用")
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="它怎么配置？",
        history_turns=(),
    )
    assert result.intent is IntentKind.STANDALONE
    assert result.rewritten_query == "它怎么配置？"
    assert llm.calls == 0


@pytest.mark.anyio
async def test_follow_up_with_anaphoric_hint_calls_llm() -> None:
    llm = StubRewriteLlm(result="ESB 总线的版本管理如何使用")
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="它的版本管理怎么用？",
        history_turns=(turn("什么是 ESB 总线？"),),
    )
    assert result.intent is IntentKind.FOLLOW_UP
    assert result.rewritten_query == "ESB 总线的版本管理如何使用"
    assert result.prompt_version == "query-rewrite-v1"
    assert llm.calls == 1


@pytest.mark.anyio
async def test_short_follow_up_without_standalone_marker_calls_llm() -> None:
    llm = StubRewriteLlm(result="改写结果")
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="接着呢",
        history_turns=(turn("还有什么"),),
    )
    assert result.intent is IntentKind.FOLLOW_UP
    assert result.rewritten_query == "改写结果"
    assert llm.calls == 1


@pytest.mark.anyio
async def test_llm_failure_degrades_gracefully() -> None:
    llm = StubRewriteLlm(result=RuntimeError("provider unavailable"))
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="它怎么用？",
        history_turns=(turn("上次的"),),
    )
    assert result.intent is IntentKind.STANDALONE
    assert result.rewritten_query == "它怎么用？"
    assert llm.calls == 1


@pytest.mark.anyio
async def test_empty_llm_output_degrades_to_standalone() -> None:
    llm = StubRewriteLlm(result="   ")
    rewriter = QueryRewriter(provider=llm)
    result = await rewriter.rewrite(
        question="那呢？",
        history_turns=(turn("上次的问题"),),
    )
    assert result.intent is IntentKind.STANDALONE
    assert result.rewritten_query == "那呢？"
    assert llm.calls == 1


@pytest.mark.anyio
async def test_blank_question_raises() -> None:
    llm = StubRewriteLlm(result="不该")
    rewriter = QueryRewriter(provider=llm)
    with pytest.raises(ValueError, match="must not be blank"):
        await rewriter.rewrite(question="  ", history_turns=(turn("history"),))


def test_zero_max_history_turns_raises() -> None:
    llm = StubRewriteLlm(result="result")
    with pytest.raises(ValueError, match="must be positive"):
        QueryRewriter(provider=llm, max_history_turns=0)


@pytest.mark.anyio
async def test_max_history_turns_truncates() -> None:
    """When history is longer than max_history_turns, only recent turns are
    passed to the LLM."""
    captured_history: tuple[QueryRewriteTurn, ...] = ()

    class CapturingLlm:
        @property
        def rewrite_prompt_version(self) -> str:
            return "query-rewrite-v1"

        async def rewrite_query(
            self,
            *,
            question: str,
            history_turns: tuple[QueryRewriteTurn, ...],
        ) -> str:
            del question
            nonlocal captured_history
            captured_history = history_turns
            return "改写结果"

    rewriter = QueryRewriter(provider=CapturingLlm(), max_history_turns=2)
    result = await rewriter.rewrite(
        question="它怎么样？",
        history_turns=tuple(turn(f"第{i}轮") for i in range(1, 5)),
    )
    assert result.intent is IntentKind.FOLLOW_UP
    assert tuple(item.content for item in captured_history) == ("第3轮", "第4轮")


@pytest.mark.anyio
async def test_follow_up_passes_assistant_answer_to_rewrite_provider() -> None:
    captured_history: tuple[QueryRewriteTurn, ...] = ()

    class CapturingLlm(StubRewriteLlm):
        async def rewrite_query(
            self,
            *,
            question: str,
            history_turns: tuple[QueryRewriteTurn, ...],
        ) -> str:
            del question
            nonlocal captured_history
            captured_history = history_turns
            return "ESB 发布流程中的审核步骤是什么意思？"

    result = await QueryRewriter(provider=CapturingLlm("unused")).rewrite(
        question="上一步是什么意思？",
        history_turns=(
            turn("ESB 怎么发布？"),
            turn("先审核，再发布。", ConversationMessageRole.ASSISTANT),
        ),
    )

    assert result.intent is IntentKind.FOLLOW_UP
    assert [item.role for item in captured_history] == [
        ConversationMessageRole.USER,
        ConversationMessageRole.ASSISTANT,
    ]
