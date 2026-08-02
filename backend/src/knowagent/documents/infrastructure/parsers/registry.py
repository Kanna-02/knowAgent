from __future__ import annotations

from knowagent.documents.errors import DocumentParseError, ParseErrorCode
from knowagent.documents.infrastructure.parsers.base import ParserLimits, normalized_extension
from knowagent.documents.infrastructure.parsers.docx_parser import DocxDocumentParser
from knowagent.documents.infrastructure.parsers.markdown_parser import MarkdownDocumentParser
from knowagent.documents.infrastructure.parsers.pdf_parser import PdfDocumentParser
from knowagent.documents.infrastructure.parsers.xlsx_parser import XlsxDocumentParser
from knowagent.documents.ports import DocumentParser


class ParserRegistry:
    def __init__(self, parsers: tuple[DocumentParser, ...]) -> None:
        if not parsers:
            raise ValueError("at least one parser is required")
        self._parsers = parsers

    @classmethod
    def default(cls, limits: ParserLimits | None = None) -> ParserRegistry:
        effective_limits = limits or ParserLimits()
        return cls(
            (
                PdfDocumentParser(effective_limits),
                DocxDocumentParser(effective_limits),
                MarkdownDocumentParser(effective_limits),
                XlsxDocumentParser(effective_limits),
            )
        )

    def resolve(self, *, filename: str, media_type: str) -> DocumentParser:
        for parser in self._parsers:
            if parser.supports(filename=filename, media_type=media_type):
                return parser
        raise DocumentParseError(
            ParseErrorCode.UNSUPPORTED_FORMAT,
            f"不支持的文档格式：{normalized_extension(filename) or '无扩展名'}",
        )
