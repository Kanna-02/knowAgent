from __future__ import annotations

import re
from io import BytesIO
from uuid import UUID

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

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
    column_letter,
    make_parsed_document,
    make_table_row_block,
    normalized_extension,
    normalized_media_type,
    validate_office_archive,
)

HEADING_STYLE = re.compile(r"heading\s*(\d+)", re.IGNORECASE)


class DocxDocumentParser:
    source_type = SourceType.DOCX

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def supports(self, *, media_type: str, filename: str) -> bool:
        expected = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return (
            normalized_extension(filename) == ".docx"
            and normalized_media_type(media_type) == expected
        )

    def parse(  # pylint: disable=too-many-locals
        self,
        *,
        content: bytes,
        document_id: UUID,
        document_version_id: UUID,
    ) -> ParsedDocument:
        validate_office_archive(content, self._limits)
        context = DocumentContext(document_id, document_version_id)
        try:
            document = Document(BytesIO(content))
        except (PackageNotFoundError, KeyError, ValueError, OSError, SyntaxError) as exc:
            raise DocumentParseError(ParseErrorCode.INVALID_FILE, "Word 文件结构无效") from exc

        blocks: list[ParsedBlock] = []
        heading_path: list[str] = []
        paragraph_index = 0
        table_index = 0
        for element in document.iter_inner_content():
            if isinstance(element, Paragraph):
                paragraph_index += 1
                text = _normalize_text(element.text)
                if not text:
                    continue
                heading_level = _heading_level(element)
                block_type = BlockType.PARAGRAPH
                if heading_level is not None:
                    heading_path[heading_level - 1 :] = []
                    while len(heading_path) < heading_level - 1:
                        heading_path.append("")
                    heading_path.append(text)
                    block_type = BlockType.HEADING
                self._append_block(
                    blocks,
                    _paragraph_block(
                        blocks=blocks,
                        block_type=block_type,
                        text=text,
                        heading_path=tuple(item for item in heading_path if item),
                        paragraph_index=paragraph_index,
                        context=context,
                    ),
                )
            elif isinstance(element, Table):
                table_index += 1
                for row_index, row in enumerate(element.rows, start=1):
                    values = tuple(_normalize_text(cell.text) for cell in row.cells)
                    if not any(values):
                        continue
                    block_index = len(blocks)
                    cell_range = f"A{row_index}:{column_letter(len(values))}{row_index}"
                    locator = SourceLocator(
                        document_id=context.document_id,
                        document_version_id=context.document_version_id,
                        source_type=SourceType.DOCX,
                        block_index=block_index,
                        heading_path=tuple(item for item in heading_path if item),
                        table_index=table_index,
                        table_row_start=row_index,
                        table_row_end=row_index,
                        cell_range=cell_range,
                    )
                    self._append_block(
                        blocks,
                        make_table_row_block(
                            block_index=block_index,
                            source_type=SourceType.DOCX,
                            text=" | ".join(values),
                            locator=locator,
                            table_id=table_index,
                            row_index=row_index,
                            is_header=row_index == 1,
                        ),
                    )

        if not blocks:
            raise DocumentParseError(ParseErrorCode.EMPTY_DOCUMENT, "Word 文件没有可索引内容")
        return make_parsed_document(
            context=context,
            source_type=self.source_type,
            blocks=blocks,
            parser_name="python-docx",
            distribution="python-docx",
        )

    def _append_block(self, blocks: list[ParsedBlock], block: ParsedBlock) -> None:
        if len(blocks) >= self._limits.max_docx_blocks:
            raise DocumentParseError(
                ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Word 结构块数量超过解析上限",
            )
        blocks.append(block)


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _heading_level(paragraph: Paragraph) -> int | None:
    style_id = paragraph.style.style_id if paragraph.style is not None else ""
    style_name = paragraph.style.name if paragraph.style is not None else ""
    matched = HEADING_STYLE.fullmatch(style_id or "") or HEADING_STYLE.fullmatch(style_name or "")
    return int(matched.group(1)) if matched else None


def _paragraph_block(  # pylint: disable=too-many-arguments
    *,
    blocks: list[ParsedBlock],
    block_type: BlockType,
    text: str,
    heading_path: tuple[str, ...],
    paragraph_index: int,
    context: DocumentContext,
) -> ParsedBlock:
    block_index = len(blocks)
    locator = SourceLocator(
        document_id=context.document_id,
        document_version_id=context.document_version_id,
        source_type=SourceType.DOCX,
        block_index=block_index,
        heading_path=heading_path,
        paragraph_start=paragraph_index,
        paragraph_end=paragraph_index,
    )
    return ParsedBlock(
        block_index=block_index,
        block_type=block_type,
        source_type=SourceType.DOCX,
        text=text,
        locator=locator,
    )
