from __future__ import annotations

import math
from uuid import uuid4

import pytest
from pydantic import ValidationError

from knowagent.documents.domain.models import SourceLocator, SourceType


def locator_ids() -> dict[str, object]:
    return {
        "document_id": uuid4(),
        "document_version_id": uuid4(),
        "block_index": 0,
    }


@pytest.mark.parametrize(
    ("source_type", "fields"),
    [
        (SourceType.PDF, {"page_number": 1, "bounding_box": (1.0, 2.0, 3.0, 4.0)}),
        (
            SourceType.DOCX,
            {"heading_path": ("接入指南",), "paragraph_start": 2, "paragraph_end": 2},
        ),
        (
            SourceType.MARKDOWN,
            {
                "heading_path": ("接入指南",),
                "paragraph_start": 1,
                "paragraph_end": 1,
                "line_start": 3,
                "line_end": 4,
            },
        ),
        (SourceType.XLSX, {"sheet_name": "参数", "cell_range": "A2:C3"}),
    ],
)
def test_source_locator_accepts_each_supported_shape(
    source_type: SourceType, fields: dict[str, object]
) -> None:
    locator = SourceLocator(source_type=source_type, **locator_ids(), **fields)

    assert locator.source_type is source_type
    assert locator.block_index == 0
    assert locator.model_dump(mode="json")["source_type"] == source_type.value


@pytest.mark.parametrize(
    ("source_type", "fields"),
    [
        (SourceType.PDF, {}),
        (SourceType.DOCX, {"heading_path": ("标题",)}),
        (
            SourceType.MARKDOWN,
            {"heading_path": (), "paragraph_start": 1, "paragraph_end": 1},
        ),
        (SourceType.XLSX, {"sheet_name": "参数"}),
        (SourceType.TICKET, {}),
    ],
)
def test_source_locator_rejects_missing_format_specific_fields(
    source_type: SourceType, fields: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        SourceLocator(source_type=source_type, **locator_ids(), **fields)


def test_source_locator_rejects_inverted_ranges_and_cross_format_fields() -> None:
    with pytest.raises(ValidationError, match="paragraph_start"):
        SourceLocator(
            source_type=SourceType.DOCX,
            **locator_ids(),
            heading_path=(),
            paragraph_start=4,
            paragraph_end=3,
        )

    with pytest.raises(ValidationError, match="not valid for pdf"):
        SourceLocator(
            source_type=SourceType.PDF,
            **locator_ids(),
            page_number=1,
            sheet_name="参数",
            cell_range="A1",
        )

    with pytest.raises(ValidationError, match="finite"):
        SourceLocator(
            source_type=SourceType.PDF,
            **locator_ids(),
            page_number=1,
            bounding_box=(0.0, 0.0, math.inf, 1.0),
        )


@pytest.mark.parametrize(
    ("source_type", "fields"),
    [
        (
            SourceType.DOCX,
            {
                "paragraph_start": 1,
                "paragraph_end": 1,
                "table_index": 1,
                "table_row_start": 1,
                "table_row_end": 1,
                "cell_range": "A1:B1",
            },
        ),
        (
            SourceType.MARKDOWN,
            {
                "paragraph_start": 1,
                "paragraph_end": 1,
                "line_start": 1,
                "line_end": 1,
                "table_index": 1,
            },
        ),
        (
            SourceType.XLSX,
            {"sheet_name": "参数", "cell_range": "A1:B1", "table_index": 1},
        ),
    ],
)
def test_source_locator_rejects_ambiguous_or_partial_table_locations(
    source_type: SourceType, fields: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        SourceLocator(source_type=source_type, **locator_ids(), **fields)


def test_ticket_locator_uses_ticket_identity_without_fake_document_ids() -> None:
    ticket_id = uuid4()

    locator = SourceLocator(
        source_type=SourceType.TICKET,
        block_index=0,
        ticket_id=ticket_id,
    )

    assert locator.ticket_id == ticket_id
    assert locator.document_id is None
    assert locator.document_version_id is None


def test_ticket_locator_rejects_document_identity() -> None:
    with pytest.raises(ValidationError, match="document"):
        SourceLocator(
            document_id=uuid4(),
            document_version_id=uuid4(),
            source_type=SourceType.TICKET,
            block_index=0,
            ticket_id=uuid4(),
        )
