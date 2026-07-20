from fieldforge_contracts import ChunkingStrategy, DocumentPage
from fieldforge_ingestion import chunk_pages


def test_chunk_pages_produces_provenance_offsets():
    page = DocumentPage(document_id="doc-1", page_number=1, text="word " * 500)
    chunks = chunk_pages([page], chunk_tokens=50, overlap_tokens=10)

    assert chunks, "expected at least one chunk"
    for chunk in chunks:
        assert chunk.document_id == "doc-1"
        assert chunk.page_number == 1
        assert chunk.strategy == ChunkingStrategy.FIXED_TOKEN
        assert chunk.start_offset < chunk.end_offset
        assert chunk.text == page.text[chunk.start_offset : chunk.end_offset]


def test_chunk_pages_skips_blank_pages():
    pages = [
        DocumentPage(document_id="doc-1", page_number=1, text="   \n  "),
        DocumentPage(document_id="doc-1", page_number=2, text="real content here"),
    ]
    chunks = chunk_pages(pages)
    assert all(c.page_number == 2 for c in chunks)
    assert len(chunks) == 1


def test_chunk_pages_rejects_overlap_not_smaller_than_chunk_size():
    page = DocumentPage(document_id="doc-1", page_number=1, text="a b c")
    try:
        chunk_pages([page], chunk_tokens=10, overlap_tokens=10)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_chunk_sequence_numbers_are_monotonic_within_document():
    page = DocumentPage(document_id="doc-1", page_number=1, text="word " * 300)
    chunks = chunk_pages([page], chunk_tokens=50, overlap_tokens=10)
    sequences = [c.sequence for c in chunks]
    assert sequences == sorted(sequences)
