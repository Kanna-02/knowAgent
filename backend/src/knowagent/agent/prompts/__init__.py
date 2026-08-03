from __future__ import annotations

from datetime import datetime
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field

from knowagent.agent.domain.models import PromptDefinition

_PROMPT_RESOURCES = {
    "grounded-answer-v1": "grounded_answer_v1.json",
}


class _PromptPayload(BaseModel):  # pylint: disable=too-few-public-methods
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content: str = Field(min_length=1)
    enabled: bool
    created_at: datetime
    change_note: str = Field(min_length=1)


def load_prompt_definition(version: str) -> PromptDefinition:
    resource_name = _PROMPT_RESOURCES.get(version)
    if resource_name is None:
        raise ValueError(f"unknown prompt version: {version}")
    resource = files(__package__).joinpath(resource_name)
    payload = _PromptPayload.model_validate_json(resource.read_text(encoding="utf-8"))
    if payload.version != version:
        raise ValueError("prompt resource version does not match its registry key")
    if not payload.enabled:
        raise ValueError(f"prompt version is disabled: {version}")
    return PromptDefinition(
        scenario=payload.scenario,
        version=payload.version,
        content=payload.content,
        enabled=payload.enabled,
        created_at=payload.created_at,
        change_note=payload.change_note,
    )


__all__ = ["load_prompt_definition"]
