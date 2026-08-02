from __future__ import annotations

from enum import StrEnum


class ParseErrorCode(StrEnum):
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INVALID_FILE = "INVALID_FILE"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    OCR_REQUIRED = "OCR_REQUIRED"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    DECODING_ERROR = "DECODING_ERROR"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"


class DocumentParseError(Exception):
    def __init__(self, code: ParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class IngestionLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the ingestion lease."""
