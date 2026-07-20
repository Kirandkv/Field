from fieldforge_contracts import Chunk, ChunkingStrategy, RetrievalResult
from fieldforge_model_adapters import ExtractiveAnswerAdapter


def _result(text: str, score: float = 1.0) -> RetrievalResult:
    chunk = Chunk(
        document_id="doc-1",
        page_number=3,
        strategy=ChunkingStrategy.FIXED_TOKEN,
        text=text,
        start_offset=0,
        end_offset=len(text),
        sequence=0,
    )
    return RetrievalResult(chunk=chunk, score=score, rank=1, retriever="bm25")


def test_refuses_when_no_evidence():
    adapter = ExtractiveAnswerAdapter()
    answer = adapter.generate("any question", [])
    assert answer.refused is True
    assert answer.citations == []


def test_answer_only_contains_substrings_of_retrieved_chunks():
    adapter = ExtractiveAnswerAdapter()
    evidence = [_result("the methane sensor calibration interval is ninety days")]
    answer = adapter.generate("calibration interval?", evidence)
    assert not answer.refused
    assert "ninety days" in answer.text
    assert len(answer.citations) == 1
    assert answer.citations[0].page_number == 3


def test_citation_carries_required_provenance_fields():
    adapter = ExtractiveAnswerAdapter()
    evidence = [_result("some evidence text")]
    answer = adapter.generate("q", evidence)
    citation = answer.citations[0]
    assert citation.source_id == "doc-1"
    assert citation.chunk_id == evidence[0].chunk.id
    assert citation.retrieval_score == evidence[0].score
    assert citation.producing_component == "extractive-v1"
