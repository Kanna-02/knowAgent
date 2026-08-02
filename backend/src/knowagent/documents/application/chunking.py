from __future__ import annotations

import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from knowagent.documents.domain.models import (
    KnowledgeChunk,
    ParsedBlock,
    ParsedDocument,
    SourceLocator,
    SourceType,
)
from knowagent.platform.settings import DocumentProcessingSettings

TOKEN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|[A-Za-z0-9_]+|[^\s]")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    max_tokens: int = DocumentProcessingSettings().chunk_max_tokens
    overlap_blocks: int = DocumentProcessingSettings().chunk_overlap_blocks

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.overlap_blocks < 0:
            raise ValueError("overlap_blocks must not be negative")

    @classmethod
    def from_settings(cls, settings: DocumentProcessingSettings) -> ChunkingConfig:
        return cls(
            max_tokens=settings.chunk_max_tokens,
            overlap_blocks=settings.chunk_overlap_blocks,
        )


@dataclass(frozen=True, slots=True)
class _ChunkDraft:
    text: str
    structure_path: tuple[str, ...]
    locators: tuple[SourceLocator, ...]


class StructureAwareChunker:  # pylint: disable=too-few-public-methods
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self._config = config or ChunkingConfig()

    def chunk(self, document: ParsedDocument) -> tuple[KnowledgeChunk, ...]:
        drafts: list[_ChunkDraft] = []
        for group in _contiguous_groups(document.blocks):
            if group[0].table_id is not None:
                drafts.extend(self._chunk_table(group))
            else:
                drafts.extend(self._chunk_regular(group))
        return tuple(
            KnowledgeChunk(
                ordinal=ordinal,
                text=draft.text,
                token_count=_token_count(draft.text),
                structure_path=draft.structure_path,
                locators=draft.locators,
            )
            for ordinal, draft in enumerate(drafts)
        )

    def _chunk_regular(self, blocks: Sequence[ParsedBlock]) -> list[_ChunkDraft]:
        drafts: list[_ChunkDraft] = []
        current: list[ParsedBlock] = []
        for block in blocks:
            if _token_count(block.text) > self._config.max_tokens:
                if current:
                    drafts.append(_draft_from_blocks(current))
                    current = []
                drafts.extend(_split_block(block, self._config.max_tokens))
                continue

            candidate = [*current, block]
            if current and _token_count(_join_blocks(candidate)) > self._config.max_tokens:
                drafts.append(_draft_from_blocks(current))
                current = (
                    current[-self._config.overlap_blocks :] if self._config.overlap_blocks else []
                )
                while (
                    current
                    and _token_count(_join_blocks([*current, block])) > self._config.max_tokens
                ):
                    current.pop(0)
            current.append(block)
        if current:
            drafts.append(_draft_from_blocks(current))
        return drafts

    def _chunk_table(self, blocks: Sequence[ParsedBlock]) -> list[_ChunkDraft]:
        header = next((block for block in blocks if block.table_header), None)
        data_rows = [block for block in blocks if block is not header]
        if not data_rows:
            return self._chunk_regular(blocks)

        drafts: list[_ChunkDraft] = []
        if header is not None and _token_count(header.text) >= self._config.max_tokens:
            drafts.extend(_split_block(header, self._config.max_tokens))
            header = None
        current: list[ParsedBlock] = [header] if header is not None else []
        for row in data_rows:
            candidate = [*current, row]
            if (
                len(current) > (1 if header is not None else 0)
                and _token_count(_join_blocks(candidate)) > self._config.max_tokens
            ):
                drafts.append(_draft_from_blocks(current))
                current = [header] if header is not None else []
                candidate = [*current, row]
            if _token_count(_join_blocks(candidate)) <= self._config.max_tokens:
                current.append(row)
                continue

            available = self._config.max_tokens
            if header is not None:
                available -= _token_count(header.text)
            if available <= 0:
                if current:
                    drafts.append(_draft_from_blocks(current))
                current = []
                available = self._config.max_tokens
            for piece in _split_text(row.text, available):
                piece_blocks = (
                    [header] if header is not None and available < self._config.max_tokens else []
                )
                locators = tuple(block.locator for block in piece_blocks) + (row.locator,)
                text_parts = [block.text for block in piece_blocks] + [piece]
                drafts.append(
                    _ChunkDraft(
                        text="\n".join(text_parts),
                        structure_path=_structure_path(row),
                        locators=_unique_locators(locators),
                    )
                )
            current = [header] if header is not None else []
        minimum_size = 1 if header is not None else 0
        if len(current) > minimum_size:
            drafts.append(_draft_from_blocks(current))
        return drafts


def _contiguous_groups(blocks: Sequence[ParsedBlock]) -> list[list[ParsedBlock]]:
    groups: list[list[ParsedBlock]] = []
    for block in blocks:
        key = _boundary_key(block)
        if not groups or _boundary_key(groups[-1][0]) != key:
            groups.append([block])
        else:
            groups[-1].append(block)
    return groups


def _boundary_key(block: ParsedBlock) -> tuple[Hashable, ...]:
    locator = block.locator
    if block.source_type is SourceType.PDF:
        return (SourceType.PDF, locator.page_number)
    if block.source_type is SourceType.XLSX:
        return (SourceType.XLSX, locator.sheet_name, block.table_id)
    return (block.source_type, locator.heading_path, block.table_id)


def _structure_path(block: ParsedBlock) -> tuple[str, ...]:
    locator = block.locator
    if locator.heading_path:
        return locator.heading_path
    if locator.sheet_name:
        return (locator.sheet_name,)
    return ()


def _draft_from_blocks(blocks: Sequence[ParsedBlock]) -> _ChunkDraft:
    return _ChunkDraft(
        text=_join_blocks(blocks),
        structure_path=_structure_path(blocks[0]),
        locators=_unique_locators(tuple(block.locator for block in blocks)),
    )


def _join_blocks(blocks: Sequence[ParsedBlock]) -> str:
    separator = "\n" if blocks and blocks[0].table_id is not None else "\n\n"
    return separator.join(block.text for block in blocks)


def _token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def _split_text(text: str, max_tokens: int) -> tuple[str, ...]:
    matches = list(TOKEN_PATTERN.finditer(text))
    if len(matches) <= max_tokens:
        return (text.strip(),)
    pieces: list[str] = []
    for start in range(0, len(matches), max_tokens):
        selected = matches[start : start + max_tokens]
        start_offset = selected[0].start()
        end_offset = selected[-1].end()
        pieces.append(text[start_offset:end_offset].strip())
    return tuple(piece for piece in pieces if piece)


def _split_block(block: ParsedBlock, max_tokens: int) -> list[_ChunkDraft]:
    return [
        _ChunkDraft(
            text=piece,
            structure_path=_structure_path(block),
            locators=(block.locator,),
        )
        for piece in _split_text(block.text, max_tokens)
    ]


def _unique_locators(locators: tuple[SourceLocator, ...]) -> tuple[SourceLocator, ...]:
    result: list[SourceLocator] = []
    seen: set[SourceLocator] = set()
    for locator in locators:
        if locator not in seen:
            seen.add(locator)
            result.append(locator)
    return tuple(result)
