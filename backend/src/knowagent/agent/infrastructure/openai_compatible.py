from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from knowagent.agent.domain.models import GenerationEvent, GenerationRequest, PromptDefinition
from knowagent.common.errors import ProviderUnavailableError


class OpenAiCompatibleLlmProvider:  # pylint: disable=too-many-arguments
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        prompt: PromptDefinition,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ValueError("LLM provider configuration is incomplete")
        if timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive")
        if not prompt.enabled:
            raise ValueError("LLM prompt must be enabled")
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._prompt = prompt
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

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
