from __future__ import annotations

import os
import re
from dataclasses import dataclass


def _environment_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class ModelServiceSettings:  # pylint: disable=too-many-instance-attributes
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    embedding_model_version: str = "ollama-bge-m3-79076464"
    ollama_model_digest: str = "79076464"
    embedding_dimension: int = 1024
    ollama_timeout_seconds: float = 300.0
    ollama_health_timeout_seconds: float = 5.0
    ollama_batch_size: int = 1
    max_request_texts: int = 32
    max_text_chars: int = 12_000
    max_total_text_chars: int = 48_000
    ollama_max_concurrency: int = 1
    ollama_keep_alive: str = "24h"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_model_version: str = "BAAI-bge-reranker-v2-m3"
    rerank_batch_size: int = 4
    rerank_max_length: int = 512
    rerank_max_concurrency: int = 1
    rerank_use_fp16: bool = False
    rerank_device: str | None = None
    rerank_max_documents: int = 20
    rerank_max_query_chars: int = 2_000
    rerank_max_document_chars: int = 12_000
    rerank_max_total_document_chars: int = 48_000
    host: str = "127.0.0.1"
    port: int = 8100

    def __post_init__(self) -> None:
        text_values = (
            self.ollama_base_url,
            self.embedding_model,
            self.embedding_model_version,
            self.ollama_model_digest,
            self.ollama_keep_alive,
            self.rerank_model,
            self.rerank_model_version,
            self.host,
        )
        if any(not value.strip() for value in text_values):
            raise ValueError("model-service text settings must not be blank")
        normalized_digest = self.ollama_model_digest.lower().removeprefix("sha256:")
        if (
            not 8 <= len(normalized_digest) <= 64
            or re.fullmatch(r"[0-9a-f]+", normalized_digest) is None
        ):
            raise ValueError("Ollama model digest must be an 8-64 character hex prefix")
        if not self.embedding_model_version.lower().endswith(normalized_digest):
            raise ValueError("embedding model version must end with the Ollama digest prefix")
        positive_values = (
            self.embedding_dimension,
            self.ollama_timeout_seconds,
            self.ollama_health_timeout_seconds,
            self.ollama_batch_size,
            self.max_request_texts,
            self.max_text_chars,
            self.max_total_text_chars,
            self.ollama_max_concurrency,
            self.rerank_batch_size,
            self.rerank_max_length,
            self.rerank_max_concurrency,
            self.rerank_max_documents,
            self.rerank_max_query_chars,
            self.rerank_max_document_chars,
            self.rerank_max_total_document_chars,
            self.port,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("model-service numeric settings must be positive")
        if self.ollama_batch_size > self.max_request_texts:
            raise ValueError("Ollama batch size must not exceed request text limit")
        if self.rerank_device is not None and not self.rerank_device.strip():
            raise ValueError("rerank device must be omitted or non-blank")
        if self.port > 65_535:
            raise ValueError("model-service port must be at most 65535")

    @classmethod
    def from_environment(cls) -> ModelServiceSettings:
        return cls(
            ollama_base_url=os.getenv(
                "KNOWAGENT_MODEL_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
            ).strip(),
            embedding_model=os.getenv("KNOWAGENT_MODEL_EMBEDDING_MODEL", "bge-m3").strip(),
            embedding_model_version=os.getenv(
                "KNOWAGENT_MODEL_EMBEDDING_VERSION", "ollama-bge-m3-79076464"
            ).strip(),
            ollama_model_digest=os.getenv(
                "KNOWAGENT_MODEL_OLLAMA_MODEL_DIGEST", "79076464"
            ).strip(),
            embedding_dimension=int(os.getenv("KNOWAGENT_MODEL_EMBEDDING_DIMENSION", "1024")),
            ollama_timeout_seconds=float(
                os.getenv("KNOWAGENT_MODEL_OLLAMA_TIMEOUT_SECONDS", "300")
            ),
            ollama_health_timeout_seconds=float(
                os.getenv("KNOWAGENT_MODEL_OLLAMA_HEALTH_TIMEOUT_SECONDS", "5")
            ),
            ollama_batch_size=int(os.getenv("KNOWAGENT_MODEL_OLLAMA_BATCH_SIZE", "1")),
            max_request_texts=int(os.getenv("KNOWAGENT_MODEL_MAX_REQUEST_TEXTS", "32")),
            max_text_chars=int(os.getenv("KNOWAGENT_MODEL_MAX_TEXT_CHARS", "12000")),
            max_total_text_chars=int(os.getenv("KNOWAGENT_MODEL_MAX_TOTAL_TEXT_CHARS", "48000")),
            ollama_max_concurrency=int(os.getenv("KNOWAGENT_MODEL_OLLAMA_MAX_CONCURRENCY", "1")),
            ollama_keep_alive=os.getenv("KNOWAGENT_MODEL_OLLAMA_KEEP_ALIVE", "24h").strip(),
            rerank_model=os.getenv(
                "KNOWAGENT_MODEL_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"
            ).strip(),
            rerank_model_version=os.getenv(
                "KNOWAGENT_MODEL_RERANK_MODEL_VERSION", "BAAI-bge-reranker-v2-m3"
            ).strip(),
            rerank_batch_size=int(os.getenv("KNOWAGENT_MODEL_RERANK_BATCH_SIZE", "4")),
            rerank_max_length=int(os.getenv("KNOWAGENT_MODEL_RERANK_MAX_LENGTH", "512")),
            rerank_max_concurrency=int(os.getenv("KNOWAGENT_MODEL_RERANK_MAX_CONCURRENCY", "1")),
            rerank_use_fp16=_environment_bool("KNOWAGENT_MODEL_RERANK_USE_FP16", False),
            rerank_device=(os.getenv("KNOWAGENT_MODEL_RERANK_DEVICE", "").strip() or None),
            rerank_max_documents=int(os.getenv("KNOWAGENT_MODEL_RERANK_MAX_DOCUMENTS", "20")),
            rerank_max_query_chars=int(os.getenv("KNOWAGENT_MODEL_RERANK_MAX_QUERY_CHARS", "2000")),
            rerank_max_document_chars=int(
                os.getenv("KNOWAGENT_MODEL_RERANK_MAX_DOCUMENT_CHARS", "12000")
            ),
            rerank_max_total_document_chars=int(
                os.getenv("KNOWAGENT_MODEL_RERANK_MAX_TOTAL_DOCUMENT_CHARS", "48000")
            ),
            host=os.getenv("KNOWAGENT_MODEL_HOST", "127.0.0.1").strip(),
            port=int(os.getenv("KNOWAGENT_MODEL_PORT", "8100")),
        )
