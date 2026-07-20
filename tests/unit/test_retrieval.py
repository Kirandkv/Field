from fieldforge_contracts import Chunk, ChunkingStrategy, RetrievalResult
from fieldforge_retrieval import BM25Index, NullEmbeddingAdapter, reciprocal_rank_fusion


def _chunk(text: str, doc_id: str = "doc-1", seq: int = 0) -> Chunk:
    return Chunk(
        document_id=doc_id,
        page_number=1,
        strategy=ChunkingStrategy.FIXED_TOKEN,
        text=text,
        start_offset=0,
        end_offset=len(text),
        sequence=seq,
    )


def test_bm25_ranks_more_relevant_chunk_higher():
    index = BM25Index()
    chunks = [
        _chunk("methane sensor calibration interval is ninety days", seq=0),
        _chunk("the robot has a battery and a camera", seq=1),
    ]
    index.build(chunks)
    results = index.search("methane sensor calibration", k=2)
    assert results
    assert results[0].chunk.sequence == 0
    assert results[0].rank == 1


def test_bm25_empty_index_returns_empty():
    index = BM25Index()
    index.build([])
    assert index.search("anything", k=5) == []


def test_bm25_search_excludes_zero_score_results():
    index = BM25Index()
    index.build([_chunk("apples and oranges")])
    results = index.search("completely unrelated automotive engineering query", k=5)
    assert results == []


def test_null_embedding_adapter_reports_unavailable_and_refuses_to_embed():
    adapter = NullEmbeddingAdapter()
    assert adapter.available is False
    try:
        adapter.embed(["text"])
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_rrf_is_passthrough_for_single_ranked_list():
    results = [RetrievalResult(chunk=_chunk("a"), score=1.0, rank=1, retriever="bm25")]
    fused = reciprocal_rank_fusion([results])
    assert fused == results


def test_rrf_combines_two_ranked_lists_by_reciprocal_rank():
    c1, c2 = _chunk("a", seq=0), _chunk("b", seq=1)
    list_a = [
        RetrievalResult(chunk=c1, score=2.0, rank=1, retriever="bm25"),
        RetrievalResult(chunk=c2, score=1.0, rank=2, retriever="bm25"),
    ]
    list_b = [
        RetrievalResult(chunk=c2, score=2.0, rank=1, retriever="dense"),
        RetrievalResult(chunk=c1, score=1.0, rank=2, retriever="dense"),
    ]
    fused = reciprocal_rank_fusion([list_a, list_b])
    assert len(fused) == 2
    assert {r.chunk.id for r in fused} == {c1.id, c2.id}
    assert fused[0].retriever == "rrf"
