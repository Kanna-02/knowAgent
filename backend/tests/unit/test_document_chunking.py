from __future__ import annotations

from uuid import uuid4

from knowagent.documents.application.chunking import ChunkingConfig, StructureAwareChunker
from knowagent.documents.domain.models import (
    BlockType,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
    SourceType,
)


def make_block(
    *,
    index: int,
    text: str,
    page: int | None = None,
    heading_path: tuple[str, ...] = (),
    sheet_name: str | None = None,
    cell_range: str | None = None,
    table_id: int | None = None,
    table_header: bool = False,
) -> ParsedBlock:
    document_id = TEST_DOCUMENT_ID
    version_id = TEST_VERSION_ID
    if page is not None:
        locator = SourceLocator(
            document_id=document_id,
            document_version_id=version_id,
            source_type=SourceType.PDF,
            block_index=index,
            page_number=page,
        )
        source_type = SourceType.PDF
    elif sheet_name is not None:
        locator = SourceLocator(
            document_id=document_id,
            document_version_id=version_id,
            source_type=SourceType.XLSX,
            block_index=index,
            sheet_name=sheet_name,
            cell_range=cell_range,
            table_index=table_id,
            table_row_start=index + 1 if table_id is not None else None,
            table_row_end=index + 1 if table_id is not None else None,
        )
        source_type = SourceType.XLSX
    else:
        locator = SourceLocator(
            document_id=document_id,
            document_version_id=version_id,
            source_type=SourceType.DOCX,
            block_index=index,
            heading_path=heading_path,
            paragraph_start=index + 1,
            paragraph_end=index + 1,
        )
        source_type = SourceType.DOCX
    return ParsedBlock(
        block_index=index,
        block_type=BlockType.TABLE_ROW if table_id is not None else BlockType.PARAGRAPH,
        text=text,
        locator=locator,
        table_id=table_id,
        table_row_index=index + 1 if table_id is not None else None,
        table_header=table_header,
        source_type=source_type,
    )


TEST_DOCUMENT_ID = uuid4()
TEST_VERSION_ID = uuid4()


def document(source_type: SourceType, blocks: list[ParsedBlock]) -> ParsedDocument:
    return ParsedDocument(
        document_id=TEST_DOCUMENT_ID,
        document_version_id=TEST_VERSION_ID,
        source_type=source_type,
        blocks=tuple(blocks),
        parser_name="test-parser",
        parser_version="1",
        schema_version="1",
    )


def test_chunker_never_crosses_pdf_pages_or_heading_paths() -> None:
    chunker = StructureAwareChunker(ChunkingConfig(max_tokens=100, overlap_blocks=0))
    pdf_chunks = chunker.chunk(
        document(
            SourceType.PDF,
            [
                make_block(index=0, text="第一页第一段", page=1),
                make_block(index=1, text="第一页第二段", page=1),
                make_block(index=2, text="第二页", page=2),
            ],
        )
    )
    docx_chunks = chunker.chunk(
        document(
            SourceType.DOCX,
            [
                make_block(index=0, text="认证说明", heading_path=("认证",)),
                make_block(index=1, text="超时说明", heading_path=("超时",)),
            ],
        )
    )

    assert len(pdf_chunks) == 2
    assert [{locator.page_number for locator in chunk.locators} for chunk in pdf_chunks] == [
        {1},
        {2},
    ]
    assert len(docx_chunks) == 2
    assert [chunk.structure_path for chunk in docx_chunks] == [("认证",), ("超时",)]


def test_chunker_splits_oversized_block_without_losing_locator() -> None:
    block = make_block(index=0, text="alpha beta gamma delta", heading_path=("限制",))
    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=2, overlap_blocks=0)).chunk(
        document(SourceType.DOCX, [block])
    )

    assert [chunk.text for chunk in chunks] == ["alpha beta", "gamma delta"]
    assert all(chunk.locators == (block.locator,) for chunk in chunks)
    assert all(chunk.token_count <= 2 for chunk in chunks)


def test_chunker_counts_contiguous_chinese_conservatively() -> None:
    text = "这是一个很长的中文段落" * 10
    block = make_block(index=0, text=text, heading_path=("限制",))

    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=10, overlap_blocks=0)).chunk(
        document(SourceType.DOCX, [block])
    )

    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == text
    assert all(chunk.token_count <= 10 for chunk in chunks)


def test_chunker_repeats_table_header_and_keeps_sheet_ranges() -> None:
    blocks = [
        make_block(
            index=0,
            text="参数 | 默认值",
            sheet_name="参数",
            cell_range="A1:B1",
            table_id=1,
            table_header=True,
        ),
        make_block(
            index=1,
            text="timeout | 30",
            sheet_name="参数",
            cell_range="A2:B2",
            table_id=1,
        ),
        make_block(
            index=2,
            text="retries | 3",
            sheet_name="参数",
            cell_range="A3:B3",
            table_id=1,
        ),
    ]
    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=9, overlap_blocks=0)).chunk(
        document(SourceType.XLSX, blocks)
    )

    assert len(chunks) == 2
    assert all(chunk.text.startswith("参数 | 默认值") for chunk in chunks)
    assert [locator.cell_range for locator in chunks[1].locators] == ["A1:B1", "A3:B3"]
    assert all({locator.sheet_name for locator in chunk.locators} == {"参数"} for chunk in chunks)


def test_chunker_splits_oversized_table_header_within_hard_budget() -> None:
    blocks = [
        make_block(
            index=0,
            text="header has four words",
            sheet_name="参数",
            cell_range="A1:B1",
            table_id=1,
            table_header=True,
        ),
        make_block(
            index=1,
            text="data row",
            sheet_name="参数",
            cell_range="A2:B2",
            table_id=1,
        ),
    ]

    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=2, overlap_blocks=0)).chunk(
        document(SourceType.XLSX, blocks)
    )

    assert [chunk.text for chunk in chunks] == ["header has", "four words", "data row"]
    assert all(chunk.token_count <= 2 for chunk in chunks)


def test_chunker_overlaps_regular_blocks_only_within_budget() -> None:
    blocks = [
        make_block(index=0, text="first block", heading_path=("限制",)),
        make_block(index=1, text="second block", heading_path=("限制",)),
        make_block(index=2, text="third block", heading_path=("限制",)),
    ]

    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=5, overlap_blocks=1)).chunk(
        document(SourceType.DOCX, blocks)
    )

    assert [chunk.text for chunk in chunks] == [
        "first block\n\nsecond block",
        "second block\n\nthird block",
    ]
    assert [[locator.block_index for locator in chunk.locators] for chunk in chunks] == [
        [0, 1],
        [1, 2],
    ]


def test_chunker_splits_oversized_table_row_and_repeats_header() -> None:
    blocks = [
        make_block(
            index=0,
            text="name value",
            sheet_name="参数",
            cell_range="A1:B1",
            table_id=1,
            table_header=True,
        ),
        make_block(
            index=1,
            text="alpha beta gamma delta",
            sheet_name="参数",
            cell_range="A2:B2",
            table_id=1,
        ),
    ]

    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=4, overlap_blocks=0)).chunk(
        document(SourceType.XLSX, blocks)
    )

    assert [chunk.text for chunk in chunks] == [
        "name value\nalpha beta",
        "name value\ngamma delta",
    ]
    assert all(chunk.token_count <= 4 for chunk in chunks)


def test_chunker_splits_table_with_only_an_oversized_header() -> None:
    header = make_block(
        index=0,
        text="header has four words",
        sheet_name="参数",
        cell_range="A1:B1",
        table_id=1,
        table_header=True,
    )

    chunks = StructureAwareChunker(ChunkingConfig(max_tokens=2, overlap_blocks=0)).chunk(
        document(SourceType.XLSX, [header])
    )

    assert [chunk.text for chunk in chunks] == ["header has", "four words"]
    assert all(chunk.locators == (header.locator,) for chunk in chunks)
