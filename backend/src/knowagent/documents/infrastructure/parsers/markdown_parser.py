from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from markdown_it import MarkdownIt
from markdown_it.token import Token

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
    ensure_file_size,
    make_parsed_document,
    make_table_row_block,
    normalized_extension,
    normalized_media_type,
)


@dataclass(frozen=True, slots=True)
class _TableRow:
    text: str
    row_index: int
    column_count: int
    line_start: int
    line_end: int
    is_header: bool


@dataclass(frozen=True, slots=True)
class _SourceLineRange:
    start: int
    end: int


class MarkdownDocumentParser:
    source_type = SourceType.MARKDOWN

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()
        self._markdown = MarkdownIt("commonmark").enable("table")

    def supports(self, *, media_type: str, filename: str) -> bool:
        return normalized_extension(filename) == ".md" and normalized_media_type(media_type) in {
            "text/markdown",
            "text/plain",
        }

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
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentParseError(
                ParseErrorCode.DECODING_ERROR,
                "Markdown 必须使用 UTF-8 编码",
            ) from exc
        tokens = self._markdown.parse(source)
        blocks = self._tokens_to_blocks(tokens, context)
        if not blocks:
            raise DocumentParseError(ParseErrorCode.EMPTY_DOCUMENT, "Markdown 没有可索引内容")
        return make_parsed_document(
            context=context,
            source_type=self.source_type,
            blocks=blocks,
            parser_name="markdown-it-py",
            distribution="markdown-it-py",
        )

    def _tokens_to_blocks(  # pylint: disable=too-many-locals
        self,
        tokens: Sequence[Token],
        context: DocumentContext,
    ) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        heading_path: list[str] = []
        paragraph_index = 0
        list_depth = 0
        table_index = 0
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.type in {"bullet_list_open", "ordered_list_open"}:
                list_depth += 1
            elif token.type in {"bullet_list_close", "ordered_list_close"}:
                list_depth -= 1
            elif token.type == "heading_open" and index + 1 < len(tokens):
                inline = tokens[index + 1]
                text = _inline_text(inline)
                level = int(token.tag.removeprefix("h"))
                heading_path[level - 1 :] = []
                while len(heading_path) < level - 1:
                    heading_path.append("")
                heading_path.append(text)
                paragraph_index += 1
                self._append_block(
                    blocks,
                    _markdown_block(
                        blocks=blocks,
                        block_type=BlockType.HEADING,
                        text=text,
                        heading_path=tuple(item for item in heading_path if item),
                        paragraph_index=paragraph_index,
                        line_range=_line_range(token),
                        context=context,
                    ),
                )
                index += 2
                continue
            elif token.type == "paragraph_open" and index + 1 < len(tokens):
                inline = tokens[index + 1]
                text = _inline_text(inline)
                if text:
                    paragraph_index += 1
                    self._append_block(
                        blocks,
                        _markdown_block(
                            blocks=blocks,
                            block_type=(
                                BlockType.LIST_ITEM if list_depth > 0 else BlockType.PARAGRAPH
                            ),
                            text=text,
                            heading_path=tuple(item for item in heading_path if item),
                            paragraph_index=paragraph_index,
                            line_range=_line_range(token),
                            context=context,
                        ),
                    )
                index += 2
                continue
            elif token.type in {"fence", "code_block"}:
                text = token.content.rstrip()
                if text:
                    paragraph_index += 1
                    self._append_block(
                        blocks,
                        _markdown_block(
                            blocks=blocks,
                            block_type=BlockType.CODE,
                            text=text,
                            heading_path=tuple(item for item in heading_path if item),
                            paragraph_index=paragraph_index,
                            line_range=_line_range(token),
                            context=context,
                        ),
                    )
            elif token.type == "table_open":
                table_index += 1
                rows, closing_index = _table_rows(tokens, index)
                for row in rows:
                    paragraph_index += 1
                    block_index = len(blocks)
                    locator = SourceLocator(
                        document_id=context.document_id,
                        document_version_id=context.document_version_id,
                        source_type=SourceType.MARKDOWN,
                        block_index=block_index,
                        heading_path=tuple(item for item in heading_path if item),
                        paragraph_start=paragraph_index,
                        paragraph_end=paragraph_index,
                        line_start=row.line_start,
                        line_end=row.line_end,
                        table_index=table_index,
                        table_row_start=row.row_index,
                        table_row_end=row.row_index,
                        cell_range=(
                            f"A{row.row_index}:{column_letter(row.column_count)}{row.row_index}"
                        ),
                    )
                    self._append_block(
                        blocks,
                        make_table_row_block(
                            block_index=block_index,
                            source_type=SourceType.MARKDOWN,
                            text=row.text,
                            locator=locator,
                            table_id=table_index,
                            row_index=row.row_index,
                            is_header=row.is_header,
                        ),
                    )
                index = closing_index + 1
                continue
            index += 1
        return blocks

    def _append_block(self, blocks: list[ParsedBlock], block: ParsedBlock) -> None:
        if len(blocks) >= self._limits.max_markdown_blocks:
            raise DocumentParseError(
                ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Markdown 结构块数量超过解析上限",
            )
        blocks.append(block)


def _inline_text(token: Token) -> str:
    if token.children:
        return "".join(
            child.content if child.type not in {"softbreak", "hardbreak"} else "\n"
            for child in token.children
        ).strip()
    return token.content.strip()


def _line_range(token: Token) -> tuple[int, int]:
    if token.map is None:
        raise DocumentParseError(ParseErrorCode.INVALID_FILE, "Markdown token 缺少源行定位")
    start, end = token.map
    return start + 1, max(start + 1, end)


def _markdown_block(  # pylint: disable=too-many-arguments
    *,
    blocks: list[ParsedBlock],
    block_type: BlockType,
    text: str,
    heading_path: tuple[str, ...],
    paragraph_index: int,
    line_range: tuple[int, int],
    context: DocumentContext,
) -> ParsedBlock:
    block_index = len(blocks)
    locator = SourceLocator(
        document_id=context.document_id,
        document_version_id=context.document_version_id,
        source_type=SourceType.MARKDOWN,
        block_index=block_index,
        heading_path=heading_path,
        paragraph_start=paragraph_index,
        paragraph_end=paragraph_index,
        line_start=line_range[0],
        line_end=line_range[1],
    )
    return ParsedBlock(
        block_index=block_index,
        block_type=block_type,
        source_type=SourceType.MARKDOWN,
        text=text,
        locator=locator,
    )


def _table_rows(tokens: Sequence[Token], opening_index: int) -> tuple[list[_TableRow], int]:
    rows: list[_TableRow] = []
    cells: list[str] = []
    in_header = False
    row_index = 0
    row_line_range: _SourceLineRange | None = None
    index = opening_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token.type == "thead_open":
            in_header = True
        elif token.type == "thead_close":
            in_header = False
        elif token.type == "tr_open":
            cells = []
            line_start, line_end = _line_range(token)
            row_line_range = _SourceLineRange(line_start, line_end)
        elif token.type == "inline":
            cells.append(_inline_text(token))
        elif token.type == "tr_close":
            current_line_range = _required_table_line_range(row_line_range)
            row_index += 1
            rows.append(
                _TableRow(
                    text=" | ".join(cells),
                    row_index=row_index,
                    column_count=max(1, len(cells)),
                    line_start=current_line_range.start,
                    line_end=current_line_range.end,
                    is_header=in_header,
                )
            )
        elif token.type == "table_close":
            return rows, index
        index += 1
    raise DocumentParseError(ParseErrorCode.INVALID_FILE, "Markdown 表格结构不完整")


def _required_table_line_range(value: _SourceLineRange | None) -> _SourceLineRange:
    if value is None:
        raise DocumentParseError(ParseErrorCode.INVALID_FILE, "Markdown 表格行缺少源行定位")
    return value
