from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

DEFAULT_RETRIEVAL_PROFILE_NAME = "default"
DEFAULT_RETRIEVAL_PROFILE_VERSION = "profile-v1"


class ConversationMessageRole(StrEnum):
    """Role of a stored conversation message."""

    USER = "user"
    ASSISTANT = "assistant"


class IntentKind(StrEnum):
    """High-level classification produced by the query rewriter.

    ``FOLLOW_UP`` means the current question depends on prior turns and was
    rewritten into a self-contained retrieval query. ``STANDALONE`` means the
    question was used as-is. The kind drives whether conversation history is
    injected into the prompt and is recorded for later analysis without
    introducing a persistent intent taxonomy.
    """

    FOLLOW_UP = "follow_up"
    STANDALONE = "standalone"


@dataclass(frozen=True, slots=True)
class QueryRewriteTurn:
    """A bounded historical message supplied only to query rewriting."""

    role: ConversationMessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("query rewrite history content must not be blank")


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """A single message persisted on a conversation turn."""

    id: UUID
    conversation_id: UUID
    role: ConversationMessageRole
    content: str
    intent: IntentKind | None
    rewritten_query: str | None
    rewrite_prompt_version: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("conversation message content must not be blank")
        if self.rewritten_query is not None and not self.rewritten_query.strip():
            raise ValueError("rewritten query must not be blank")
        if self.rewrite_prompt_version is not None and not self.rewrite_prompt_version.strip():
            raise ValueError("rewrite prompt version must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("conversation message time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Conversation:
    """A multi-turn conversation scoped to an account and business system."""

    id: UUID
    system_id: UUID
    account_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("conversation title must not be blank")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("conversation timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class QueryRewriteResult:
    """Output of the intent-aware query rewriter.

    ``rewritten_query`` is always set: when the question is standalone it
    equals the normalized original question. ``intent`` records whether a
    rewrite occurred and is surfaced to the client for transparency.
    """

    intent: IntentKind
    rewritten_query: str
    original_query: str
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        if not self.rewritten_query.strip() or not self.original_query.strip():
            raise ValueError("query rewrite inputs must not be blank")
        if self.prompt_version is not None and not self.prompt_version.strip():
            raise ValueError("query rewrite prompt version must not be blank")


@dataclass(frozen=True, slots=True)
class RetrievalProfile:  # pylint: disable=too-many-instance-attributes
    """A named, versioned bundle of retrieval parameters.

    Mirrors the scalar fields on ``RetrievalSettings`` so a request can select
    a named profile instead of the process-wide defaults. ``is_active`` marks
    the profile currently applied when no explicit profile is requested.
    """

    name: str
    version: str
    keyword_top_k: int
    vector_top_k: int
    result_top_k: int
    rrf_k: int
    keyword_weight: float
    vector_weight: float
    rerank_candidate_top_k: int
    rerank_top_k: int
    evidence_max_items: int
    evidence_max_characters: int
    is_active: bool
    created_at: datetime
    change_note: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip() or not self.change_note.strip():
            raise ValueError("retrieval profile metadata must not be blank")
        limits = (
            self.keyword_top_k,
            self.vector_top_k,
            self.result_top_k,
            self.rrf_k,
            self.rerank_candidate_top_k,
            self.rerank_top_k,
            self.evidence_max_items,
            self.evidence_max_characters,
        )
        if any(value <= 0 for value in limits):
            raise ValueError("retrieval profile limits must be positive")
        if self.result_top_k > self.keyword_top_k + self.vector_top_k:
            raise ValueError("retrieval profile result_top_k exceeds candidate budget")
        if not self.result_top_k <= self.rerank_top_k <= self.rerank_candidate_top_k:
            raise ValueError("retrieval profile rerank limits must cover the result limit")
        if self.rerank_candidate_top_k > self.keyword_top_k + self.vector_top_k:
            raise ValueError("retrieval profile rerank candidate limit exceeds budget")
        weights = (self.keyword_weight, self.vector_weight)
        if any(not math.isfinite(value) or value <= 0 for value in weights):
            raise ValueError("retrieval profile weights must be positive and finite")
        if self.created_at.tzinfo is None:
            raise ValueError("retrieval profile created_at must be timezone-aware")


__all__ = [
    "Conversation",
    "ConversationMessage",
    "ConversationMessageRole",
    "DEFAULT_RETRIEVAL_PROFILE_NAME",
    "DEFAULT_RETRIEVAL_PROFILE_VERSION",
    "IntentKind",
    "QueryRewriteTurn",
    "QueryRewriteResult",
    "RetrievalProfile",
]
