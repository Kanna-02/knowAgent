from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from knowagent.documents.domain.models import SourceLocator, SourceType
from knowagent.retrieval.application.evidence import EvidenceOrganizer
from knowagent.retrieval.domain.models import FusedSearchHit, SearchHit


def make_hit(*, text: str, rank: int = 1) -> FusedSearchHit:
    raw = SearchHit(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text=text,
        locators=(
            SourceLocator(
                document_id=uuid4(),
                document_version_id=uuid4(),
                source_type=SourceType.PDF,
                block_index=0,
                page_number=7,
            ),
        ),
        source_name="ESB 运维手册.pdf",
        source_version="3",
        score=0.8,
    )
    return FusedSearchHit.from_search_hit(
        raw,
        fused_score=1.0 / (60 + rank),
        channels=("keyword",),
    )


def test_organize_assigns_stable_ids_and_keeps_source_snapshots() -> None:
    organizer = EvidenceOrganizer(max_items=3, max_characters=500)

    bundle = organizer.organize((make_hit(text="重启前先备份配置。"),))

    assert bundle.prompt_text.startswith("[E1]")
    assert bundle.items[0].evidence_id == "E1"
    assert bundle.items[0].source_name == "ESB 运维手册.pdf"
    assert bundle.items[0].source_version == "3"
    assert bundle.items[0].quoted_text == "重启前先备份配置。"
    assert bundle.items[0].locators[0].page_number == 7


def test_organize_respects_item_and_character_budgets_without_partial_evidence() -> None:
    organizer = EvidenceOrganizer(max_items=2, max_characters=12)
    first = make_hit(text="123456")
    second = make_hit(text="abcdef", rank=2)
    third = make_hit(text="ignored", rank=3)

    bundle = organizer.organize((first, second, third))

    assert [item.quoted_text for item in bundle.items] == ["123456", "abcdef"]
    assert "ignored" not in bundle.prompt_text


def test_organize_rejects_candidates_without_verifiable_locations() -> None:
    invalid = replace(make_hit(text="不可定位"), locators=())

    with pytest.raises(ValueError, match="locator"):
        EvidenceOrganizer(max_items=2, max_characters=100).organize((invalid,))


def test_organize_skips_oversized_candidate_and_keeps_later_evidence_that_fits() -> None:
    organizer = EvidenceOrganizer(max_items=2, max_characters=12)

    bundle = organizer.organize(
        (
            make_hit(text="this candidate is too long"),
            make_hit(text="fits", rank=2),
            make_hit(text="also-fits", rank=3),
        )
    )

    assert [item.quoted_text for item in bundle.items] == ["fits"]
