from __future__ import annotations

import math
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    XLSX = "xlsx"
    TICKET = "ticket"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    CODE = "code"
    TABLE_ROW = "table_row"


class SourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: UUID
    document_version_id: UUID
    source_type: SourceType
    block_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    bounding_box: tuple[float, float, float, float] | None = None
    heading_path: tuple[str, ...] = ()
    paragraph_start: int | None = Field(default=None, ge=1)
    paragraph_end: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    table_index: int | None = Field(default=None, ge=1)
    table_row_start: int | None = Field(default=None, ge=1)
    table_row_end: int | None = Field(default=None, ge=1)
    sheet_name: str | None = None
    cell_range: str | None = None
    ticket_id: UUID | None = None

    @model_validator(mode="after")
    def validate_source_shape(self) -> SourceLocator:
        self._validate_ordered_pair("paragraph_start", self.paragraph_start, self.paragraph_end)
        self._validate_ordered_pair("line_start", self.line_start, self.line_end)
        self._validate_ordered_pair("table_row_start", self.table_row_start, self.table_row_end)
        if self.bounding_box is not None:
            left, top, right, bottom = self.bounding_box
            if not all(math.isfinite(value) for value in self.bounding_box):
                raise ValueError("bounding_box values must be finite")
            if right < left or bottom < top:
                raise ValueError("bounding_box must use left, top, right, bottom order")

        allowed_fields = self._allowed_fields()
        present_fields = {
            name for name, value in self._format_values().items() if value not in (None, (), "")
        }
        invalid_fields = sorted(present_fields - allowed_fields)
        if invalid_fields:
            joined = ", ".join(invalid_fields)
            raise ValueError(f"{joined} not valid for {self.source_type.value}")

        {
            SourceType.PDF: self._validate_pdf_location,
            SourceType.DOCX: self._validate_docx_location,
            SourceType.MARKDOWN: self._validate_markdown_location,
            SourceType.XLSX: self._validate_xlsx_location,
            SourceType.TICKET: self._validate_ticket_location,
        }[self.source_type]()
        return self

    def _validate_pdf_location(self) -> None:
        if self.page_number is None:
            raise ValueError("page_number is required for pdf")

    def _validate_docx_location(self) -> None:
        has_paragraph = self.paragraph_start is not None and self.paragraph_end is not None
        table_values = (
            self.table_index,
            self.table_row_start,
            self.table_row_end,
            self.cell_range,
        )
        has_any_table_value = any(value not in (None, "") for value in table_values)
        has_table_row = all(value not in (None, "") for value in table_values)
        if has_any_table_value and not has_table_row:
            raise ValueError("docx table location fields must be provided together")
        if has_paragraph and has_table_row:
            raise ValueError("docx paragraph and table locations are mutually exclusive")
        if not (has_paragraph or has_table_row):
            raise ValueError("docx requires a paragraph range or a table row location")

    def _validate_markdown_location(self) -> None:
        if self.paragraph_start is None or self.paragraph_end is None:
            raise ValueError("paragraph range is required for markdown")
        if self.line_start is None or self.line_end is None:
            raise ValueError("source line range is required for markdown")
        table_values = (
            self.table_index,
            self.table_row_start,
            self.table_row_end,
            self.cell_range,
        )
        if any(value not in (None, "") for value in table_values) and not all(
            value not in (None, "") for value in table_values
        ):
            raise ValueError("markdown table location fields must be provided together")

    def _validate_xlsx_location(self) -> None:
        if not (self.sheet_name and self.cell_range):
            raise ValueError("sheet_name and cell_range are required for xlsx")
        table_values = (self.table_index, self.table_row_start, self.table_row_end)
        if any(value is not None for value in table_values) and not all(
            value is not None for value in table_values
        ):
            raise ValueError("xlsx table location fields must be provided together")

    def _validate_ticket_location(self) -> None:
        if self.ticket_id is None:
            raise ValueError("ticket_id is required for ticket")

    @staticmethod
    def _validate_ordered_pair(name: str, start: int | None, end: int | None) -> None:
        if (start is None) != (end is None):
            raise ValueError(f"{name} and its end field must be provided together")
        if start is not None and end is not None and start > end:
            raise ValueError(f"{name} must not be greater than its end field")

    def _allowed_fields(self) -> set[str]:
        return {
            SourceType.PDF: {"page_number", "bounding_box"},
            SourceType.DOCX: {
                "heading_path",
                "paragraph_start",
                "paragraph_end",
                "table_index",
                "table_row_start",
                "table_row_end",
                "cell_range",
            },
            SourceType.MARKDOWN: {
                "heading_path",
                "paragraph_start",
                "paragraph_end",
                "line_start",
                "line_end",
                "table_index",
                "table_row_start",
                "table_row_end",
                "cell_range",
            },
            SourceType.XLSX: {
                "sheet_name",
                "cell_range",
                "table_index",
                "table_row_start",
                "table_row_end",
            },
            SourceType.TICKET: {"ticket_id"},
        }[self.source_type]

    def _format_values(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "heading_path": self.heading_path,
            "paragraph_start": self.paragraph_start,
            "paragraph_end": self.paragraph_end,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "table_index": self.table_index,
            "table_row_start": self.table_row_start,
            "table_row_end": self.table_row_end,
            "sheet_name": self.sheet_name,
            "cell_range": self.cell_range,
            "ticket_id": self.ticket_id,
        }


class ParsedBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    block_index: int = Field(ge=0)
    block_type: BlockType
    source_type: SourceType
    text: str = Field(min_length=1)
    locator: SourceLocator
    table_id: int | None = Field(default=None, ge=1)
    table_row_index: int | None = Field(default=None, ge=1)
    table_header: bool = False

    @model_validator(mode="after")
    def validate_block(self) -> ParsedBlock:
        if self.locator.block_index != self.block_index:
            raise ValueError("locator block_index must match block_index")
        if self.locator.source_type is not self.source_type:
            raise ValueError("locator source_type must match source_type")
        if self.block_type is BlockType.TABLE_ROW:
            if self.table_id is None or self.table_row_index is None:
                raise ValueError("table rows require table_id and table_row_index")
        elif self.table_id is not None or self.table_row_index is not None or self.table_header:
            raise ValueError("table metadata is only valid for table rows")
        return self


class ParsedDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: UUID
    document_version_id: UUID
    source_type: SourceType
    blocks: tuple[ParsedBlock, ...]
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_blocks(self) -> ParsedDocument:
        for expected_index, block in enumerate(self.blocks):
            locator = block.locator
            if block.block_index != expected_index:
                raise ValueError("blocks must have contiguous zero-based indexes")
            if block.source_type is not self.source_type:
                raise ValueError("all blocks must use the document source_type")
            if locator.document_id != self.document_id:
                raise ValueError("all locators must use the document_id")
            if locator.document_version_id != self.document_version_id:
                raise ValueError("all locators must use the document_version_id")
        return self


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    structure_path: tuple[str, ...] = ()
    locators: tuple[SourceLocator, ...] = Field(min_length=1)
