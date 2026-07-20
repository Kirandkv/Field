"""Fixed-token chunking strategy.

Only one strategy is implemented in slice 1. The chunking-strategy benchmark comparing
fixed/recursive/sentence-aware/semantic/layout-aware/parent-child/table-aware/small-to-big
is planned for M2 (see docs/ROADMAP.md) — building eight strategies before one is proven
end-to-end in the API would be premature.
"""

from __future__ import annotations

from fieldforge_contracts import Chunk, ChunkingStrategy, DocumentPage

DEFAULT_CHUNK_TOKENS = 200
DEFAULT_OVERLAP_TOKENS = 40


def chunk_pages(
    pages: list[DocumentPage],
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    if overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be smaller than chunk_tokens")

    chunks: list[Chunk] = []
    sequence = 0
    for page in pages:
        if not page.text.strip():
            continue
        tokens = _tokenize_with_offsets(page.text)
        step = chunk_tokens - overlap_tokens
        i = 0
        while i < len(tokens):
            window = tokens[i : i + chunk_tokens]
            if not window:
                break
            start_offset = window[0][1]
            end_offset = window[-1][2]
            text = page.text[start_offset:end_offset]
            chunks.append(
                Chunk(
                    document_id=page.document_id,
                    page_number=page.page_number,
                    strategy=ChunkingStrategy.FIXED_TOKEN,
                    text=text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    sequence=sequence,
                )
            )
            sequence += 1
            if i + chunk_tokens >= len(tokens):
                break
            i += step
    return chunks


def _tokenize_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Whitespace tokenization that preserves character offsets for provenance."""
    tokens: list[tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        start = i
        while i < n and not text[i].isspace():
            i += 1
        if i > start:
            tokens.append((text[start:i], start, i))
    return tokens
