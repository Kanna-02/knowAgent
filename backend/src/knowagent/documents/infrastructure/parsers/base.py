from __future__ import annotations

from dataclasses import dataclass, fields
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import PurePath
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from knowagent.documents.domain.models import (
    BlockType,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
    SourceType,
)
from knowagent.documents.errors import DocumentParseError, ParseErrorCode
from knowagent.platform.settings import DocumentProcessingSettings

OLE_COMPOUND_FILE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True, slots=True)
class DocumentContext:
    document_id: UUID
    document_version_id: UUID


@dataclass(frozen=True, slots=True)
class ParserLimits:  # pylint: disable=too-many-instance-attributes
    max_file_bytes: int = DocumentProcessingSettings().max_file_bytes
    max_archive_uncompressed_bytes: int = (
        DocumentProcessingSettings().max_archive_uncompressed_bytes
    )
    max_archive_ratio: int = DocumentProcessingSettings().max_archive_ratio
    max_archive_members: int = DocumentProcessingSettings().max_archive_members
    max_pdf_pages: int = DocumentProcessingSettings().max_pdf_pages
    max_pdf_blocks: int = DocumentProcessingSettings().max_pdf_blocks
    max_docx_blocks: int = DocumentProcessingSettings().max_docx_blocks
    max_markdown_blocks: int = DocumentProcessingSettings().max_markdown_blocks
    max_xlsx_sheets: int = DocumentProcessingSettings().max_xlsx_sheets
    max_xlsx_rows_per_sheet: int = DocumentProcessingSettings().max_xlsx_rows_per_sheet
    max_xlsx_columns: int = DocumentProcessingSettings().max_xlsx_columns
    max_xlsx_cells: int = DocumentProcessingSettings().max_xlsx_cells

    def __post_init__(self) -> None:
        for item in fields(self):
            if getattr(self, item.name) <= 0:
                raise ValueError(f"{item.name} must be positive")

    @classmethod
    def from_settings(cls, settings: DocumentProcessingSettings) -> ParserLimits:
        return cls(
            max_file_bytes=settings.max_file_bytes,
            max_archive_uncompressed_bytes=settings.max_archive_uncompressed_bytes,
            max_archive_ratio=settings.max_archive_ratio,
            max_archive_members=settings.max_archive_members,
            max_pdf_pages=settings.max_pdf_pages,
            max_pdf_blocks=settings.max_pdf_blocks,
            max_docx_blocks=settings.max_docx_blocks,
            max_markdown_blocks=settings.max_markdown_blocks,
            max_xlsx_sheets=settings.max_xlsx_sheets,
            max_xlsx_rows_per_sheet=settings.max_xlsx_rows_per_sheet,
            max_xlsx_columns=settings.max_xlsx_columns,
            max_xlsx_cells=settings.max_xlsx_cells,
        )


def ensure_file_size(content: bytes, limits: ParserLimits) -> None:
    if not content:
        raise DocumentParseError(ParseErrorCode.EMPTY_DOCUMENT, "文件内容为空")
    if len(content) > limits.max_file_bytes:
        raise DocumentParseError(ParseErrorCode.RESOURCE_LIMIT_EXCEEDED, "文件大小超过解析上限")


def validate_office_archive(content: bytes, limits: ParserLimits) -> None:
    ensure_file_size(content, limits)
    if content.startswith(OLE_COMPOUND_FILE_SIGNATURE):
        raise DocumentParseError(ParseErrorCode.PASSWORD_PROTECTED, "不支持受密码保护的文件")
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
    except (BadZipFile, OSError) as exc:
        raise DocumentParseError(ParseErrorCode.INVALID_FILE, "Office 文件结构无效") from exc

    if len(members) > limits.max_archive_members:
        raise DocumentParseError(
            ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
            "Office 文件条目数量超过解析上限",
        )

    total_size = 0
    total_compressed = 0
    for member in members:
        if member.flag_bits & 0x1:
            raise DocumentParseError(ParseErrorCode.PASSWORD_PROTECTED, "不支持受密码保护的文件")
        total_size += member.file_size
        total_compressed += member.compress_size
        if total_size > limits.max_archive_uncompressed_bytes:
            raise DocumentParseError(
                ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Office 文件展开后超过解析上限",
            )
        if member.file_size and member.compress_size == 0:
            raise DocumentParseError(
                ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Office 文件压缩比异常",
            )
        if member.file_size / max(member.compress_size, 1) > limits.max_archive_ratio:
            raise DocumentParseError(
                ParseErrorCode.RESOURCE_LIMIT_EXCEEDED,
                "Office 文件压缩比异常",
            )
    if total_size and total_compressed == 0:
        raise DocumentParseError(ParseErrorCode.RESOURCE_LIMIT_EXCEEDED, "Office 文件压缩比异常")
    if total_compressed and total_size / total_compressed > limits.max_archive_ratio:
        raise DocumentParseError(ParseErrorCode.RESOURCE_LIMIT_EXCEEDED, "Office 文件压缩比异常")


def package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def normalized_extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def normalized_media_type(media_type: str) -> str:
    return media_type.partition(";")[0].strip().lower()


def make_parsed_document(
    *,
    context: DocumentContext,
    source_type: SourceType,
    blocks: list[ParsedBlock],
    parser_name: str,
    distribution: str,
) -> ParsedDocument:
    return ParsedDocument(
        document_id=context.document_id,
        document_version_id=context.document_version_id,
        source_type=source_type,
        blocks=tuple(blocks),
        parser_name=parser_name,
        parser_version=package_version(distribution),
        schema_version="1",
    )


def make_table_row_block(  # pylint: disable=too-many-arguments
    *,
    block_index: int,
    source_type: SourceType,
    text: str,
    locator: SourceLocator,
    table_id: int,
    row_index: int,
    is_header: bool,
) -> ParsedBlock:
    return ParsedBlock(
        block_index=block_index,
        block_type=BlockType.TABLE_ROW,
        source_type=source_type,
        text=text,
        locator=locator,
        table_id=table_id,
        table_row_index=row_index,
        table_header=is_header,
    )


def column_letter(number: int) -> str:
    if number <= 0:
        raise ValueError("column number must be positive")
    result = ""
    remaining = number
    while remaining:
        remaining, remainder = divmod(remaining - 1, 26)
        result = chr(65 + remainder) + result
    return result
