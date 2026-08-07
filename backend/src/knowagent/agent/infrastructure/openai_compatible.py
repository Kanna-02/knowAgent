from __future__ import annotations

import copy
import json
import logging
from collections.abc import AsyncIterator

import httpx

from knowagent.agent.domain.conversation import QueryRewriteTurn
from knowagent.agent.domain.models import GenerationEvent, GenerationRequest, PromptDefinition
from knowagent.agent.prompts import GROUNDED_ANSWER_SCENARIO, QUERY_REWRITE_SCENARIO
from knowagent.common.errors import ProviderUnavailableError

LOGGER = logging.getLogger(__name__)


class OpenAiCompatibleLlmProvider:  # pylint: disable=too-many-arguments
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        prompt: PromptDefinition,
        rewrite_prompt: PromptDefinition | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ValueError("LLM provider configuration is incomplete")
        if timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive")
        if not prompt.enabled:
            raise ValueError("LLM prompt must be enabled")
        if prompt.scenario != GROUNDED_ANSWER_SCENARIO:
            raise ValueError("LLM answer prompt scenario is invalid")
        if rewrite_prompt is not None:
            if not rewrite_prompt.enabled:
                raise ValueError("LLM rewrite prompt must be enabled")
            if rewrite_prompt.scenario != QUERY_REWRITE_SCENARIO:
                raise ValueError("LLM rewrite prompt scenario is invalid")
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._prompt = prompt
        self._rewrite_prompt = rewrite_prompt
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    @property
    def rewrite_prompt_version(self) -> str | None:
        return self._rewrite_prompt.version if self._rewrite_prompt is not None else None

    @property
    def client(self) -> httpx.AsyncClient | None:
        """Shared HTTP client, exposed for connection-pool reuse by copies."""
        return self._client

    def with_prompt_definition(self, prompt: PromptDefinition) -> OpenAiCompatibleLlmProvider:
        """Return an immutable copy that uses the given prompt at its scenario.

        The HTTP client and configuration (url/api_key/model/timeout) are
        shared with the original so the connection pool is reused across
        concurrent requests. Only the active ``_prompt`` or ``_rewrite_prompt``
        field is replaced on the copy, so concurrent requests cannot overwrite
        each other's prompt selection. When the incoming prompt is already the
        active version with identical content the same instance is returned.
        """
        if not prompt.enabled:
            raise ValueError("LLM prompt must be enabled")
        if prompt.scenario == GROUNDED_ANSWER_SCENARIO:
            if prompt.version == self._prompt.version and prompt.content == self._prompt.content:
                return self
            clone = copy.copy(self)
            clone._prompt = prompt  # pylint: disable=protected-access
            return clone
        if prompt.scenario == QUERY_REWRITE_SCENARIO:
            if self._rewrite_prompt is not None and self._rewrite_prompt == prompt:
                return self
            clone = copy.copy(self)
            clone._rewrite_prompt = prompt  # pylint: disable=protected-access
            return clone
        raise ValueError(f"unsupported prompt scenario: {prompt.scenario}")

    async def rewrite_query(
        self,
        *,
        question: str,
        history_turns: tuple[QueryRewriteTurn, ...],
    ) -> str:
        """Merge a follow-up question with recent history into a standalone query.

        Uses a non-streaming chat completion with a dedicated system prompt.
        任何 provider or parsing failure raises ``ProviderUnavailableError`` so
        the caller can degrade to the original question.
        """
        if self._rewrite_prompt is None:
            raise ProviderUnavailableError("llm")
        messages = [
            {"role": "system", "content": self._rewrite_prompt.content},
            *[{"role": turn.role.value, "content": turn.content} for turn in history_turns],
            {"role": "user", "content": f"请改写当前问题：{question}"},
        ]
        client = self._client or httpx.AsyncClient()
        owns_client = self._client is None
        try:
            response = await client.post(
                f"{self._url}",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                raise ProviderUnavailableError("llm")
            payload = response.json()
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ProviderUnavailableError("llm")
            content = choices[0].get("message", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise ProviderUnavailableError("llm")
            return content.strip()
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            # Per AI_DEVELOPMENT_RULES §16.4, degradation must be logged.
            LOGGER.warning("query rewrite LLM provider failed: %s", error)
            raise ProviderUnavailableError("llm") from error
        finally:
            if owns_client:
                await client.aclose()

    async def generate(self, *, request: GenerationRequest) -> AsyncIterator[GenerationEvent]:
        client = self._client or httpx.AsyncClient()
        owns_client = self._client is None
        completed = False
        finish_reason: str | None = None
        try:
            async with client.stream(
                "POST",
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=self._payload(request),
                timeout=self._timeout_seconds,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ProviderUnavailableError("llm")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        if finish_reason != "stop":
                            raise ProviderUnavailableError("llm")
                        completed = True
                        yield GenerationEvent.completed()
                        break
                    event, chunk_finish_reason = self._parse_chunk(data)
                    if chunk_finish_reason is not None:
                        finish_reason = chunk_finish_reason
                    if event is not None:
                        yield event
            if not completed and finish_reason == "stop":
                yield GenerationEvent.completed()
                completed = True
            if not completed:
                raise ProviderUnavailableError("llm")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            # Per AI_DEVELOPMENT_RULES §16.4, degradation must be logged.
            LOGGER.warning("answer generation LLM provider failed: %s", error)
            raise ProviderUnavailableError("llm") from error
        finally:
            if owns_client:
                await client.aclose()

    def _payload(self, request: GenerationRequest) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._prompt.content},
                {
                    "role": "user",
                    "content": f"问题：{request.question}\n\n证据：\n{request.evidence.prompt_text}",
                },
            ],
            "temperature": 0,
            "stream": True,
            "response_format": {"type": "json_object"},
        }

    @staticmethod
    def _parse_chunk(data: str) -> tuple[GenerationEvent | None, str | None]:
        payload = json.loads(data)
        choices = payload["choices"]
        if not isinstance(choices, list) or not choices:
            return None, None
        choice = choices[0]
        if not isinstance(choice, dict):
            raise TypeError("invalid choice payload")
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            raise TypeError("invalid delta payload")
        content = delta.get("content")
        event = GenerationEvent.delta(content) if isinstance(content, str) and content else None
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise TypeError("invalid finish reason")
        return event, finish_reason
