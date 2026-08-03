from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelServiceSettings:  # pylint: disable=too-many-instance-attributes
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    embedding_model_version: str = "ollama-bge-m3-daec91ff"
    ollama_model_digest: str = "daec91ff"
    embedding_dimension: int = 1024
    ollama_timeout_seconds: float = 300.0
    ollama_health_timeout_seconds: float = 5.0
    ollama_batch_size: int = 1
    max_request_texts: int = 32
    max_text_chars: int = 12_000
    max_total_text_chars: int = 48_000
    ollama_max_concurrency: int = 1
    ollama_keep_alive: str = "24h"
    host: str = "127.0.0.1"
    port: int = 8100

    def __post_init__(self) -> None:
        text_values = (
            self.ollama_base_url,
            self.embedding_model,
            self.embedding_model_version,
            self.ollama_model_digest,
            self.ollama_keep_alive,
            self.host,
        )
        if any(not value.strip() for value in text_values):
            raise ValueError("model-service text settings must not be blank")
        normalized_digest = self.ollama_model_digest.lower().removeprefix("sha256:")
        if not 8 <= len(normalized_digest) <= 64 or re.fullmatch(
            r"[0-9a-f]+", normalized_digest
        ) is None:
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
            self.port,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("model-service numeric settings must be positive")
        if self.ollama_batch_size > self.max_request_texts:
            raise ValueError("Ollama batch size must not exceed request text limit")
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
                "KNOWAGENT_MODEL_EMBEDDING_VERSION", "ollama-bge-m3-daec91ff"
            ).strip(),
            ollama_model_digest=os.getenv(
                "KNOWAGENT_MODEL_OLLAMA_MODEL_DIGEST", "daec91ff"
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
            host=os.getenv("KNOWAGENT_MODEL_HOST", "127.0.0.1").strip(),
            port=int(os.getenv("KNOWAGENT_MODEL_PORT", "8100")),
        )
