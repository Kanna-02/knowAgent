from __future__ import annotations

from knowagent.retrieval.domain.models import EvidenceBundle, EvidenceItem, FusedSearchHit


class EvidenceOrganizer:  # pylint: disable=too-few-public-methods
    def __init__(self, *, max_items: int, max_characters: int) -> None:
        if max_items <= 0 or max_characters <= 0:
            raise ValueError("evidence budgets must be positive")
        self._max_items = max_items
        self._max_characters = max_characters

    def organize(self, hits: tuple[FusedSearchHit, ...]) -> EvidenceBundle:
        items: list[EvidenceItem] = []
        used_characters = 0
        for hit in hits:
            if len(items) >= self._max_items:
                break
            if not hit.locators:
                raise ValueError("evidence candidate must include at least one locator")
            text = hit.text.strip()
            if used_characters + len(text) > self._max_characters:
                continue
            evidence_id = f"E{len(items) + 1}"
            items.append(
                EvidenceItem(
                    evidence_id=evidence_id,
                    chunk_id=hit.chunk_id,
                    source_id=hit.source_id,
                    quoted_text=text,
                    source_name=hit.source_name,
                    source_version=hit.source_version,
                    locators=hit.locators,
                )
            )
            used_characters += len(text)
        prompt_text = "\n\n".join(
            f"[{item.evidence_id}] {item.source_name} ({item.source_version})\n"
            f"{item.quoted_text}"
            for item in items
        )
        return EvidenceBundle(items=tuple(items), prompt_text=prompt_text)
