from __future__ import annotations

import os
from dataclasses import dataclass, field, fields


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
            cookie_secure=_as_bool(os.getenv("KNOWAGENT_COOKIE_SECURE", "true")),
            login_attempts=int(os.getenv("KNOWAGENT_LOGIN_ATTEMPTS", "8")),
            login_window_seconds=int(os.getenv("KNOWAGENT_LOGIN_WINDOW_SECONDS", "900")),
            environment=os.getenv("KNOWAGENT_ENVIRONMENT", "production"),
            document_processing=DocumentProcessingSettings.from_environment(),
        )
