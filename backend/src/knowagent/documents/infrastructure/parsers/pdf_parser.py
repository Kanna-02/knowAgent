from __future__ import annotations

from typing import cast
from uuid import UUID

import fitz  # type: ignore[import-untyped]

from knowagent.documents.domain.models import (
    BlockType,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
    SourceType,
)
from knowagent.documents.errors import DocumentParseError, ParseErrorCode
from knowagent.documents.infrastructure.parsers.base import (
    DocumentContext,
    ParserLimits,
    ensure_file_size,
    make_parsed_document,
    normalized_extension,
    normalized_media_type,
)


class PdfDocumentParser:
    source_type = SourceType.PDF

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def supports(self, *, media_type: str, filename: str) -> bool:
        return (
            normalized_extension(filename) == ".pdf"
            and normalized_media_type(media_type) == "application/pdf"
        )

    def parse(
        self,
        *,
        content: bytes,
        document_id: UUID,
        document_version_id: UUID,
    ) -> ParsedDocument:
        ensure_file_size(content, self._limits)
        context = DocumentContext(document_id, document_version_id)
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise DocumentParseError(ParseErrorCode.INVALID_FILE, "PDF 文件结构无效") from exc

        try:
            if document.needs_pass:
                raise DocumentParseError(
                    ParseErrorCode.PASSWORD_PROTECTED,
                    "不支持受密码保护的 PDF",
                )
            if document.page_count > self._limits.max_pdf_pages:
                raise DocumentParseError(
                    ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                    "PDF 页数超过解析上限",
                )
            blocks = self._extract_blocks(document, context, self._limits.max_pdf_blocks)
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise DocumentParseError(ParseErrorCode.INVALID_FILE, "PDF 文件结构无效") from exc
        finally:
            document.close()

        if not blocks:
            raise DocumentParseError(
                ParseErrorCode.OCR_REQUIRED,
                "PDF 未检测到可提取文本，需要 OCR",
            )
        return make_parsed_document(
            context=context,
            source_type=self.source_type,
            blocks=blocks,
            parser_name="pymupdf",
            distribution="PyMuPDF",
        )

    @staticmethod
    def _extract_blocks(
        document: fitz.Document,
        context: DocumentContext,
        max_blocks: int,
    ) -> list[ParsedBlock]:
        parsed: list[ParsedBlock] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            raw_blocks = cast(
                list[tuple[float, float, float, float, str, int, int]], page.get_text("blocks")
            )
            raw_blocks.sort(key=lambda item: (round(item[1], 2), round(item[0], 2)))
            for raw_block in raw_blocks:
                text = "\n".join(line.strip() for line in raw_block[4].splitlines() if line.strip())
                if not text:
                    continue
                if len(parsed) >= max_blocks:
                    raise DocumentParseError(
                        ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                        "PDF 结构块数量超过解析上限",
                    )
                block_index = len(parsed)
                locator = SourceLocator(
                    document_id=context.document_id,
                    document_version_id=context.document_version_id,
                    source_type=SourceType.PDF,
                    block_index=block_index,
                    page_number=page_index + 1,
                    bounding_box=(
                        round(raw_block[0], 3),
                        round(raw_block[1], 3),
                        round(raw_block[2], 3),
                        round(raw_block[3], 3),
                    ),
                )
                parsed.append(
                    ParsedBlock(
                        block_index=block_index,
                        block_type=BlockType.PARAGRAPH,
                        source_type=SourceType.PDF,
                        text=text,
                        locator=locator,
                    )
                )
        return parsed
