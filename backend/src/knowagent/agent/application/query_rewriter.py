from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from knowagent.agent.domain.conversation import IntentKind, QueryRewriteResult, QueryRewriteTurn

LOGGER = logging.getLogger(__name__)

# Lightweight indicators that the question depends on the prior turn.
_FOLLOW_UP_HINTS = (
    "它",
    "他",
    "她",
    "这个",
    "那个",
    "上面",
    "前面",
    "刚才",
    "接着",
    "然后",
    "还有呢",
    "呢",
    "呢？",
    "呢?",
    "呢。",
)

_STANDALONE_NEGATIVE = ("什么是", "什么是", "如何", "为什么", "请", "列举", "说明", "解释")


class RewriteLlmProvider(Protocol):  # pylint: disable=too-few-public-methods
    """Minimal LLM contract for query rewriting.

    Returns the rewritten query string or raises if the provider is unavailable.
    The rewriter degrades gracefully: when the LLM call fails, the original
    question is used as-is with ``IntentKind.STANDALONE``.
    """

    async def rewrite_query(
        self,
        *,
        question: str,
        history_turns: tuple[QueryRewriteTurn, ...],
    ) -> str: ...

    @property
    def rewrite_prompt_version(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class QueryRewriter:
    """Rule-gated, LLM-backed query rewriter for multi-turn conversations.

    The rewriter first classifies whether the question looks like a follow-up
    using lightweight rules (anaphoric hints, short length, no standalone
    markers). Standalone questions skip the LLM entirely. Follow-ups call the
    LLM to merge the current question with recent history into a self-contained
    retrieval query, degrading to the original question on any provider error.
    """

    provider: RewriteLlmProvider
    max_history_turns: int = 5

    def __post_init__(self) -> None:
        if self.max_history_turns <= 0:
            raise ValueError("query rewriter max history turns must be positive")

    async def rewrite(
        self,
        *,
        question: str,
        history_turns: tuple[QueryRewriteTurn, ...],
    ) -> QueryRewriteResult:
        normalized = question.strip()
        if not normalized:
            raise ValueError("question must not be blank for rewriting")
        if not history_turns or not self._looks_like_follow_up(normalized, history_turns):
            return QueryRewriteResult(
                intent=IntentKind.STANDALONE,
                rewritten_query=normalized,
                original_query=normalized,
                prompt_version=None,
            )
        recent = history_turns[-self.max_history_turns :]
        prompt_version = self.provider.rewrite_prompt_version
        try:
            rewritten = await self.provider.rewrite_query(
                question=normalized,
                history_turns=recent,
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Per QUALITY_RULES §3.2 and AI_DEVELOPMENT_RULES §16.4, degradation
            # must be logged so operators can detect silent provider failures.
            LOGGER.warning(
                "query rewrite degraded to standalone; original question kept "
                "after LLM provider failure: %s",
                error,
            )
            return QueryRewriteResult(
                intent=IntentKind.STANDALONE,
                rewritten_query=normalized,
                original_query=normalized,
                prompt_version=prompt_version,
            )
        cleaned = rewritten.strip()
        if not cleaned:
            return QueryRewriteResult(
                intent=IntentKind.STANDALONE,
                rewritten_query=normalized,
                original_query=normalized,
                prompt_version=prompt_version,
            )
        return QueryRewriteResult(
            intent=IntentKind.FOLLOW_UP,
            rewritten_query=cleaned,
            original_query=normalized,
            prompt_version=prompt_version,
        )

    @staticmethod
    def _looks_like_follow_up(
        question: str,
        history: tuple[QueryRewriteTurn, ...],
    ) -> bool:
        if not history:
            return False
        # If the question starts with a standalone marker, treat as new topic.
        for marker in _STANDALONE_NEGATIVE:
            if question.startswith(marker):
                return False
        # Explicit anaphoric hints are strong follow-up signals.
        if any(hint in question for hint in _FOLLOW_UP_HINTS):
            return True
        # Very short questions without standalone markers are likely follow-ups.
        return len(question) <= 12


__all__ = ["QueryRewriter", "RewriteLlmProvider"]
