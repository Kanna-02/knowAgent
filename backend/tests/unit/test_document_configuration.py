from __future__ import annotations

import pytest

from knowagent.api.app import create_app
from knowagent.documents.application.chunking import ChunkingConfig
from knowagent.documents.infrastructure.parsers import ParserLimits
from knowagent.platform.settings import (
    DocumentProcessingSettings,
    EvidencePolicySettings,
    IngestionSettings,
    LlmSettings,
    ObjectStorageSettings,
    RetrievalSettings,
    Settings,
    TicketSettings,
)
from knowagent.worker.celery_app import build_celery_app


def test_document_limits_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWAGENT_DOCUMENT_MAX_FILE_BYTES", "4096")
    monkeypatch.setenv("KNOWAGENT_DOCUMENT_MAX_ARCHIVE_MEMBERS", "25")
    monkeypatch.setenv("KNOWAGENT_DOCUMENT_CHUNK_MAX_TOKENS", "128")
    monkeypatch.setenv("KNOWAGENT_DOCUMENT_CHUNK_OVERLAP_BLOCKS", "2")

    settings = Settings.from_environment()
    parser_limits = ParserLimits.from_settings(settings.document_processing)
    chunking = ChunkingConfig.from_settings(settings.document_processing)

    assert parser_limits.max_file_bytes == 4096
    assert parser_limits.max_archive_members == 25
    assert chunking == ChunkingConfig(max_tokens=128, overlap_blocks=2)


def test_document_limits_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_file_bytes"):
        DocumentProcessingSettings(max_file_bytes=0)
    with pytest.raises(ValueError, match="chunk_overlap_blocks"):
        DocumentProcessingSettings(chunk_overlap_blocks=-1)


def test_object_storage_and_ingestion_settings_load_without_leaking_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWAGENT_S3_ENDPOINT_URL", "https://storage.internal")
    monkeypatch.setenv("KNOWAGENT_S3_BUCKET", "knowagent-test")
    monkeypatch.setenv("KNOWAGENT_S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("KNOWAGENT_S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("KNOWAGENT_S3_CA_BUNDLE", "/etc/pki/company-ca.pem")
    monkeypatch.setenv("KNOWAGENT_INGESTION_LEASE_SECONDS", "120")
    monkeypatch.setenv("KNOWAGENT_INGESTION_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("KNOWAGENT_INGESTION_SOFT_TIME_LIMIT_SECONDS", "60")
    monkeypatch.setenv("KNOWAGENT_INGESTION_HARD_TIME_LIMIT_SECONDS", "90")

    settings = Settings.from_environment()

    assert settings.object_storage.configured is True
    assert settings.object_storage.verify_value == "/etc/pki/company-ca.pem"
    assert settings.ingestion.lease_seconds == 120
    assert settings.ingestion.max_attempts == 4
    assert "test-secret" not in repr(settings.object_storage)
    assert "test-access" not in repr(settings.object_storage)


def test_invalid_storage_and_ingestion_boundaries_fail_fast() -> None:
    with pytest.raises(ValueError, match="S3"):
        ObjectStorageSettings(multipart_chunk_size=0)
    with pytest.raises(ValueError, match="positive"):
        IngestionSettings(max_attempts=0)
    with pytest.raises(ValueError, match="hard time"):
        IngestionSettings(soft_time_limit_seconds=60, hard_time_limit_seconds=60)
    with pytest.raises(ValueError, match="lease"):
        IngestionSettings(lease_seconds=60, soft_time_limit_seconds=30, hard_time_limit_seconds=90)


def test_security_boolean_settings_reject_unknown_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWAGENT_S3_VERIFY_TLS", "tru")

    with pytest.raises(ValueError, match="KNOWAGENT_S3_VERIFY_TLS"):
        ObjectStorageSettings.from_environment()


def test_celery_configuration_uses_late_ack_low_prefetch_and_bounded_tasks() -> None:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://127.0.0.1:6379/7",
        redis_prefix="test",
        session_cookie_name="session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="test",
    )

    application = build_celery_app(settings)

    assert application.conf.task_acks_late is True
    assert application.conf.task_reject_on_worker_lost is True
    assert application.conf.worker_prefetch_multiplier == 1
    assert application.conf.task_soft_time_limit == 600
    assert application.conf.task_time_limit == 660
    assert application.conf.beat_schedule["recover-ingestion-jobs"]["task"] == (
        "knowagent.ingestion.recover"
    )


def test_api_dispatcher_uses_the_resolved_application_broker() -> None:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://127.0.0.1:6379/7",
        redis_prefix="test",
        session_cookie_name="session",
        session_ttl_seconds=3600,
        cookie_secure=True,
        login_attempts=4,
        login_window_seconds=60,
        environment="test",
    )

    application = create_app(settings)

    assert application.state.ingestion_dispatcher.broker_url == settings.redis_url
    application.state.engine.dispose()


def test_llm_and_retrieval_settings_load_user_compatible_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("LLM_API_KEY", "local-secret")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("KNOWAGENT_LLM_PROMPT_VERSION", "grounded-answer-v1")
    monkeypatch.setenv("KNOWAGENT_EMBEDDING_API_BASE", "http://model-service:8100/v1")
    monkeypatch.setenv("KNOWAGENT_EMBEDDING_MODEL", "bge-m3")
    monkeypatch.setenv("KNOWAGENT_EMBEDDING_BATCH_SIZE", "16")
    monkeypatch.setenv("KNOWAGENT_RERANK_API_BASE", "http://rerank:8100/v1")
    monkeypatch.setenv("KNOWAGENT_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    monkeypatch.setenv("KNOWAGENT_RERANK_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("KNOWAGENT_RETRIEVAL_RESULT_TOP_K", "6")
    monkeypatch.setenv("KNOWAGENT_RETRIEVAL_RERANK_TOP_K", "8")
    monkeypatch.setenv("KNOWAGENT_RETRIEVAL_KEYWORD_WEIGHT", "1.5")
    monkeypatch.setenv("KNOWAGENT_RETRIEVAL_VECTOR_WEIGHT", "2")
    monkeypatch.setenv("KNOWAGENT_EVIDENCE_POLICY_VERSION", "esb-evidence-v2")
    monkeypatch.setenv("KNOWAGENT_EVIDENCE_MIN_FUSED_SCORE", "0.02")
    monkeypatch.setenv("KNOWAGENT_EVIDENCE_MIN_SCORE_GAP", "0.001")
    monkeypatch.setenv("KNOWAGENT_EVIDENCE_DEGRADED_SCORE_MULTIPLIER", "1.4")
    monkeypatch.setenv("KNOWAGENT_TICKET_DEDUPLICATION_WINDOW_HOURS", "48")

    settings = Settings.from_environment()

    assert settings.llm.base_url.endswith("/v1")
    assert settings.llm.model == "qwen3.6-plus"
    assert settings.llm.prompt_version == "grounded-answer-v1"
    assert settings.llm.configured is True
    assert settings.retrieval.embedding_base_url == "http://model-service:8100/v1"
    assert settings.retrieval.embedding_batch_size == 16
    assert settings.retrieval.rerank_base_url == "http://rerank:8100/v1"
    assert settings.retrieval.rerank_timeout_seconds == 7
    assert settings.retrieval.result_top_k == 6
    assert settings.retrieval.rerank_top_k == 8
    assert settings.retrieval.keyword_weight == 1.5
    assert settings.retrieval.vector_weight == 2
    assert settings.evidence_policy.policy_version == "esb-evidence-v2"
    assert settings.evidence_policy.minimum_fused_score == 0.02
    assert settings.evidence_policy.minimum_score_gap == 0.001
    assert settings.evidence_policy.degraded_score_multiplier == 1.4
    assert settings.tickets.deduplication_window_hours == 48
    assert "local-secret" not in repr(settings.llm)


def test_llm_and_retrieval_settings_reject_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="LLM timeout"):
        LlmSettings(timeout_seconds=0)
    with pytest.raises(ValueError, match="retrieval"):
        RetrievalSettings(result_top_k=0)
    with pytest.raises(ValueError, match="result_top_k"):
        RetrievalSettings(keyword_top_k=2, vector_top_k=2, result_top_k=5)
    with pytest.raises(ValueError, match="rerank limits"):
        RetrievalSettings(result_top_k=10, rerank_top_k=9)
    with pytest.raises(ValueError, match="weights"):
        RetrievalSettings(keyword_weight=0)
    with pytest.raises(ValueError, match="evidence score"):
        EvidencePolicySettings(minimum_fused_score=-0.1)
    with pytest.raises(ValueError, match="multiplier"):
        EvidencePolicySettings(degraded_score_multiplier=0.9)
    with pytest.raises(ValueError, match="finite"):
        EvidencePolicySettings(minimum_fused_score=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        EvidencePolicySettings(degraded_score_multiplier=float("inf"))
    with pytest.raises(ValueError, match="deduplication"):
        TicketSettings(deduplication_window_hours=0)


def test_retrieval_defaults_fit_cpu_embedding_request_budget() -> None:
    settings = RetrievalSettings()

    assert settings.embedding_batch_size == 4
    assert settings.embedding_timeout_seconds == 300
