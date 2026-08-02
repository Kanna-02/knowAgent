from __future__ import annotations

import pytest

from knowagent.documents.application.chunking import ChunkingConfig
from knowagent.documents.infrastructure.parsers import ParserLimits
from knowagent.platform.settings import DocumentProcessingSettings, Settings


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
