from __future__ import annotations

from typing import Protocol
from uuid import UUID

from knowagent.documents.domain.models import ParsedDocument, SourceType


class DocumentParser(Protocol):
    @property
    def source_type(self) -> SourceType: ...

    def supports(self, *, media_type: str, filename: str) -> bool: ...

    def parse(
        self,
        *,
        content: bytes,
        document_id: UUID,
        document_version_id: UUID,
    ) -> ParsedDocument: ...
