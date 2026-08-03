from __future__ import annotations

import os
from dataclasses import dataclass, field, fields


def _as_bool(value: str, *, setting_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{setting_name} must be an explicit boolean value")


@dataclass(frozen=True, slots=True)
class DocumentProcessingSettings:  # pylint: disable=too-many-instance-attributes
    max_file_bytes: int = 25 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 200 * 1024 * 1024
    max_archive_ratio: int = 100
    max_archive_members: int = 10_000
    max_pdf_pages: int = 500
    max_pdf_blocks: int = 100_000
    max_docx_blocks: int = 100_000
    max_markdown_blocks: int = 100_000
    max_xlsx_sheets: int = 50
    max_xlsx_rows_per_sheet: int = 100_000
    max_xlsx_columns: int = 256
    max_xlsx_cells: int = 1_000_000
    chunk_max_tokens: int = 512
    chunk_overlap_blocks: int = 1

    def __post_init__(self) -> None:
        for item in fields(self):
            value = int(getattr(self, item.name))
            if item.name == "chunk_overlap_blocks":
                if value < 0:
                    raise ValueError(f"{item.name} must not be negative")
            elif value <= 0:
                raise ValueError(f"{item.name} must be positive")

    @classmethod
    def from_environment(cls) -> DocumentProcessingSettings:
        return cls(
            max_file_bytes=int(
                os.getenv("KNOWAGENT_DOCUMENT_MAX_FILE_BYTES", str(25 * 1024 * 1024))
            ),
            max_archive_uncompressed_bytes=int(
                os.getenv(
                    "KNOWAGENT_DOCUMENT_MAX_ARCHIVE_UNCOMPRESSED_BYTES",
                    str(200 * 1024 * 1024),
                )
            ),
            max_archive_ratio=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_ARCHIVE_RATIO", "100")),
            max_archive_members=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_ARCHIVE_MEMBERS", "10000")),
            max_pdf_pages=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_PDF_PAGES", "500")),
            max_pdf_blocks=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_PDF_BLOCKS", "100000")),
            max_docx_blocks=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_DOCX_BLOCKS", "100000")),
            max_markdown_blocks=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_MARKDOWN_BLOCKS", "100000")),
            max_xlsx_sheets=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_XLSX_SHEETS", "50")),
            max_xlsx_rows_per_sheet=int(
                os.getenv("KNOWAGENT_DOCUMENT_MAX_XLSX_ROWS_PER_SHEET", "100000")
            ),
            max_xlsx_columns=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_XLSX_COLUMNS", "256")),
            max_xlsx_cells=int(os.getenv("KNOWAGENT_DOCUMENT_MAX_XLSX_CELLS", "1000000")),
            chunk_max_tokens=int(os.getenv("KNOWAGENT_DOCUMENT_CHUNK_MAX_TOKENS", "512")),
            chunk_overlap_blocks=int(os.getenv("KNOWAGENT_DOCUMENT_CHUNK_OVERLAP_BLOCKS", "1")),
        )


@dataclass(frozen=True, slots=True)
class ObjectStorageSettings:  # pylint: disable=too-many-instance-attributes
    endpoint_url: str = ""
    bucket: str = ""
    region: str = "us-east-1"
    access_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    verify_tls: bool = True
    ca_bundle: str | None = None
    multipart_threshold: int = 8 * 1024 * 1024
    multipart_chunk_size: int = 8 * 1024 * 1024
    connect_timeout_seconds: int = 5
    read_timeout_seconds: int = 60
    sdk_max_attempts: int = 3

    def __post_init__(self) -> None:
        values = (
            self.multipart_threshold,
            self.multipart_chunk_size,
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.sdk_max_attempts,
        )
        if any(value <= 0 for value in values):
            raise ValueError("S3 size, timeout, and retry settings must be positive")

    @property
    def configured(self) -> bool:
        return all((self.endpoint_url, self.bucket, self.access_key, self.secret_key))

    @property
    def verify_value(self) -> bool | str:
        return self.ca_bundle or self.verify_tls

    @classmethod
    def from_environment(cls) -> ObjectStorageSettings:
        ca_bundle = os.getenv("KNOWAGENT_S3_CA_BUNDLE", "").strip() or None
        return cls(
            endpoint_url=os.getenv("KNOWAGENT_S3_ENDPOINT_URL", "").strip(),
            bucket=os.getenv("KNOWAGENT_S3_BUCKET", "").strip(),
            region=os.getenv("KNOWAGENT_S3_REGION", "us-east-1").strip(),
            access_key=os.getenv("KNOWAGENT_S3_ACCESS_KEY", "").strip(),
            secret_key=os.getenv("KNOWAGENT_S3_SECRET_KEY", "").strip(),
            verify_tls=_as_bool(
                os.getenv("KNOWAGENT_S3_VERIFY_TLS", "true"),
                setting_name="KNOWAGENT_S3_VERIFY_TLS",
            ),
            ca_bundle=ca_bundle,
            multipart_threshold=int(
                os.getenv("KNOWAGENT_S3_MULTIPART_THRESHOLD", str(8 * 1024 * 1024))
            ),
            multipart_chunk_size=int(
                os.getenv("KNOWAGENT_S3_MULTIPART_CHUNK_SIZE", str(8 * 1024 * 1024))
            ),
            connect_timeout_seconds=int(os.getenv("KNOWAGENT_S3_CONNECT_TIMEOUT_SECONDS", "5")),
            read_timeout_seconds=int(os.getenv("KNOWAGENT_S3_READ_TIMEOUT_SECONDS", "60")),
            sdk_max_attempts=int(os.getenv("KNOWAGENT_S3_SDK_MAX_ATTEMPTS", "3")),
        )


@dataclass(frozen=True, slots=True)
class IngestionSettings:
    max_attempts: int = 3
    lease_seconds: int = 900
    retry_base_seconds: int = 30
    dispatch_stale_seconds: int = 60
    recovery_batch_size: int = 100
    soft_time_limit_seconds: int = 600
    hard_time_limit_seconds: int = 660

    def __post_init__(self) -> None:
        values = (
            self.max_attempts,
            self.lease_seconds,
            self.retry_base_seconds,
            self.dispatch_stale_seconds,
            self.recovery_batch_size,
            self.soft_time_limit_seconds,
            self.hard_time_limit_seconds,
        )
        if any(value <= 0 for value in values):
            raise ValueError("ingestion settings must be positive")
        if self.hard_time_limit_seconds <= self.soft_time_limit_seconds:
            raise ValueError("ingestion hard time limit must exceed soft time limit")
        if self.lease_seconds <= self.hard_time_limit_seconds:
            raise ValueError("ingestion lease must exceed hard time limit")

    @classmethod
    def from_environment(cls) -> IngestionSettings:
        return cls(
            max_attempts=int(os.getenv("KNOWAGENT_INGESTION_MAX_ATTEMPTS", "3")),
            lease_seconds=int(os.getenv("KNOWAGENT_INGESTION_LEASE_SECONDS", "900")),
            retry_base_seconds=int(os.getenv("KNOWAGENT_INGESTION_RETRY_BASE_SECONDS", "30")),
            dispatch_stale_seconds=int(
                os.getenv("KNOWAGENT_INGESTION_DISPATCH_STALE_SECONDS", "60")
            ),
            recovery_batch_size=int(os.getenv("KNOWAGENT_INGESTION_RECOVERY_BATCH_SIZE", "100")),
            soft_time_limit_seconds=int(
                os.getenv("KNOWAGENT_INGESTION_SOFT_TIME_LIMIT_SECONDS", "600")
            ),
            hard_time_limit_seconds=int(
                os.getenv("KNOWAGENT_INGESTION_HARD_TIME_LIMIT_SECONDS", "660")
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmSettings:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""
    prompt_version: str = "grounded-answer-v1"
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive")
        if not self.prompt_version.strip():
            raise ValueError("LLM prompt version must not be blank")

    @property
    def configured(self) -> bool:
        return all((self.base_url, self.api_key, self.model))

    @classmethod
    def from_environment(cls) -> LlmSettings:
        return cls(
            base_url=_preferred_environment("KNOWAGENT_LLM_API_BASE", "LLM_API_BASE"),
            api_key=_preferred_environment("KNOWAGENT_LLM_API_KEY", "LLM_API_KEY"),
            model=_preferred_environment("KNOWAGENT_LLM_MODEL", "LLM_MODEL"),
            prompt_version=os.getenv("KNOWAGENT_LLM_PROMPT_VERSION", "grounded-answer-v1").strip(),
            timeout_seconds=int(os.getenv("KNOWAGENT_LLM_TIMEOUT_SECONDS", "60")),
        )


@dataclass(frozen=True, slots=True)
class RetrievalSettings:  # pylint: disable=too-many-instance-attributes
    embedding_base_url: str = "http://127.0.0.1:8100/v1"
    embedding_model: str = "bge-m3"
    embedding_timeout_seconds: int = 15
    embedding_batch_size: int = 32
    keyword_top_k: int = 20
    vector_top_k: int = 20
    result_top_k: int = 10
    rrf_k: int = 60
    evidence_max_items: int = 6
    evidence_max_characters: int = 12_000

    def __post_init__(self) -> None:
        values = (
            self.embedding_timeout_seconds,
            self.embedding_batch_size,
            self.keyword_top_k,
            self.vector_top_k,
            self.result_top_k,
            self.rrf_k,
            self.evidence_max_items,
            self.evidence_max_characters,
        )
        if any(value <= 0 for value in values):
            raise ValueError("retrieval settings must be positive")
        if self.result_top_k > self.keyword_top_k + self.vector_top_k:
            raise ValueError("result_top_k exceeds the available retrieval candidates")
        if not self.embedding_base_url.strip() or not self.embedding_model.strip():
            raise ValueError("embedding provider settings must not be blank")

    @classmethod
    def from_environment(cls) -> RetrievalSettings:
        return cls(
            embedding_base_url=os.getenv(
                "KNOWAGENT_EMBEDDING_API_BASE", "http://127.0.0.1:8100/v1"
            ).strip(),
            embedding_model=os.getenv("KNOWAGENT_EMBEDDING_MODEL", "bge-m3").strip(),
            embedding_timeout_seconds=int(os.getenv("KNOWAGENT_EMBEDDING_TIMEOUT_SECONDS", "15")),
            embedding_batch_size=int(os.getenv("KNOWAGENT_EMBEDDING_BATCH_SIZE", "32")),
            keyword_top_k=int(os.getenv("KNOWAGENT_RETRIEVAL_KEYWORD_TOP_K", "20")),
            vector_top_k=int(os.getenv("KNOWAGENT_RETRIEVAL_VECTOR_TOP_K", "20")),
            result_top_k=int(os.getenv("KNOWAGENT_RETRIEVAL_RESULT_TOP_K", "10")),
            rrf_k=int(os.getenv("KNOWAGENT_RETRIEVAL_RRF_K", "60")),
            evidence_max_items=int(os.getenv("KNOWAGENT_EVIDENCE_MAX_ITEMS", "6")),
            evidence_max_characters=int(os.getenv("KNOWAGENT_EVIDENCE_MAX_CHARACTERS", "12000")),
        )


def _preferred_environment(primary: str, compatible: str) -> str:
    return os.getenv(primary, os.getenv(compatible, "")).strip()


@dataclass(frozen=True, slots=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    database_url: str
    redis_url: str
    redis_prefix: str
    session_cookie_name: str
    session_ttl_seconds: int
    cookie_secure: bool
    login_attempts: int
    login_window_seconds: int
    environment: str
    document_processing: DocumentProcessingSettings = field(
        default_factory=DocumentProcessingSettings
    )
    object_storage: ObjectStorageSettings = field(default_factory=ObjectStorageSettings)
    ingestion: IngestionSettings = field(default_factory=IngestionSettings)
    llm: LlmSettings = field(default_factory=LlmSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "KNOWAGENT_DATABASE_URL",
                "postgresql+psycopg://knowagent:knowagent@127.0.0.1:5432/knowagent",
            ),
            redis_url=os.getenv("KNOWAGENT_REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_prefix=os.getenv("KNOWAGENT_REDIS_PREFIX", "knowagent"),
            session_cookie_name=os.getenv("KNOWAGENT_SESSION_COOKIE", "knowagent_session"),
            session_ttl_seconds=int(os.getenv("KNOWAGENT_SESSION_TTL_SECONDS", "28800")),
            cookie_secure=_as_bool(
                os.getenv("KNOWAGENT_COOKIE_SECURE", "true"),
                setting_name="KNOWAGENT_COOKIE_SECURE",
            ),
            login_attempts=int(os.getenv("KNOWAGENT_LOGIN_ATTEMPTS", "8")),
            login_window_seconds=int(os.getenv("KNOWAGENT_LOGIN_WINDOW_SECONDS", "900")),
            environment=os.getenv("KNOWAGENT_ENVIRONMENT", "production"),
            document_processing=DocumentProcessingSettings.from_environment(),
            object_storage=ObjectStorageSettings.from_environment(),
            ingestion=IngestionSettings.from_environment(),
            llm=LlmSettings.from_environment(),
            retrieval=RetrievalSettings.from_environment(),
        )
