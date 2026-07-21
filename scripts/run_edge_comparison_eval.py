"""FieldForge Edge comparison benchmark: sparse+extractive (slice-1 default) vs
hybrid+generative (Edge mode), plus a small-vs-larger local model fallback-rate
comparison — on the real docs_qa_v1 dataset and corpus. See
docs/adr/0005-edge-offline-profile.md.

Requires Ollama running locally with nomic-embed-text and at least one chat model
pulled; degrades to "TBD" for the sections that need it if Ollama is unreachable,
per the program brief's "never invent a benchmark value" rule.

Usage: python scripts/run_edge_comparison_eval.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
from fieldforge_contracts import Document, EvaluationCase  # noqa: E402
from fieldforge_guardrails import scan_retrieved_chunks  # noqa: E402
from fieldforge_ingestion import chunk_pages, extract_pages  # noqa: E402
from fieldforge_model_adapters import (  # noqa: E402
    ExtractiveAnswerAdapter,
    ModelAdapter,
    OllamaGenerativeAdapter,
)
from fieldforge_retrieval import (  # noqa: E402
    BM25Index,
    OllamaEmbeddingAdapter,
    QdrantDenseIndex,
    reciprocal_rank_fusion,
)

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
QA_DATASET = REPO_ROOT / "evals" / "datasets" / "docs_qa_v1.jsonl"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"
COMPARISON_MODELS = ["qwen2.5:0.5b", "qwen3:1.7b"]
MODEL_COMPARISON_TRIALS = 5


def _ollama_reachable() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=1.0).status_code == 200
    except httpx.RequestError:
        return False


def _load_corpus():
    all_chunks = []
    doc_id_to_filename = {}
    for path in sorted(SAMPLES_DIR.glob("*.md")):
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        doc = Document(id=sha256, filename=path.name, content_type="text/markdown", sha256=sha256)
        pages = extract_pages(doc.id, "text/markdown", raw)
        chunks = chunk_pages(pages)
        all_chunks.extend(chunks)
        doc_id_to_filename[doc.id] = doc.filename
    return all_chunks, doc_id_to_filename


def _load_cases() -> list[EvaluationCase]:
    lines = QA_DATASET.read_text(encoding="utf-8").splitlines()
    return [EvaluationCase(**json.loads(line)) for line in lines if line.strip()]


def run_configuration(
    name: str, chunks, doc_id_to_filename, cases, use_hybrid: bool, use_generative: bool
) -> dict:
    bm25 = BM25Index()
    bm25.build(chunks)

    dense = None
    embedding_adapter = None
    if use_hybrid:
        embedding_adapter = OllamaEmbeddingAdapter()
        dense = QdrantDenseIndex(path=str(REPO_ROOT / f"scratch_edge_qdrant_{name}"))
        dense.build(chunks, embedding_adapter)

    answer_adapter: ModelAdapter
    if use_generative:
        answer_adapter = OllamaGenerativeAdapter(fallback=ExtractiveAnswerAdapter())
    else:
        answer_adapter = ExtractiveAnswerAdapter()

    hits, mrr_sum, refusal_correct, citation_ok = 0, 0.0, 0, 0
    scored_cases = 0
    actual_non_refused = 0
    latencies = []

    for case in cases:
        start = time.perf_counter()
        sparse_results = bm25.search(case.question, k=5)
        results = sparse_results
        if dense is not None and embedding_adapter is not None:
            dense_results = dense.search(case.question, k=5, embedding_adapter=embedding_adapter)
            results = reciprocal_rank_fusion([sparse_results, dense_results])[:5]
        clean_results, _ = scan_retrieved_chunks(results)

        generated = answer_adapter.generate(case.question, clean_results)
        latencies.append((time.perf_counter() - start) * 1000)

        if case.expect_refusal == generated.refused:
            refusal_correct += 1
        if case.gold_document_ids:
            scored_cases += 1
            retrieved_filenames = [doc_id_to_filename.get(r.chunk.document_id, "") for r in clean_results]
            gold = set(case.gold_document_ids)
            if gold & set(retrieved_filenames):
                hits += 1
                rank = next((i + 1 for i, fn in enumerate(retrieved_filenames) if fn in gold), None)
                if rank:
                    mrr_sum += 1.0 / rank
        if not generated.refused:
            actual_non_refused += 1
            valid_ids = {r.chunk.id for r in clean_results}
            if all(c.chunk_id in valid_ids for c in generated.citations):
                citation_ok += 1

    if dense is not None:
        dense.close()

    return {
        "config": name,
        "recall_at_5": round(hits / scored_cases, 3) if scored_cases else 0.0,
        "mrr": round(mrr_sum / scored_cases, 3) if scored_cases else 0.0,
        "refusal_accuracy": round(refusal_correct / len(cases), 3) if cases else 0.0,
        "citation_correctness": round(citation_ok / actual_non_refused, 3) if actual_non_refused else 0.0,
        "latency_ms_p50": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else 0.0,
    }


def run_model_size_comparison(chunks) -> list[dict]:
    bm25 = BM25Index()
    bm25.build(chunks)
    question = "At what methane reading does FF-R07 automatically stop during a survey?"
    results = bm25.search(question, k=3)

    comparisons = []
    for model in COMPARISON_MODELS:
        adapter = OllamaGenerativeAdapter(model=model, fallback=ExtractiveAnswerAdapter())
        fallback_count = 0
        latencies = []
        for _ in range(MODEL_COMPARISON_TRIALS):
            start = time.perf_counter()
            answer = adapter.generate(question, results)
            latencies.append((time.perf_counter() - start) * 1000)
            if not answer.citations or answer.citations[0].producing_component != adapter.name:
                fallback_count += 1
        comparisons.append(
            {
                "model": model,
                "trials": MODEL_COMPARISON_TRIALS,
                "fallback_rate": round(fallback_count / MODEL_COMPARISON_TRIALS, 3),
                "latency_ms_p50": round(sorted(latencies)[len(latencies) // 2], 3),
            }
        )
    return comparisons


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    chunks, doc_id_to_filename = _load_corpus()
    cases = _load_cases()

    report: dict = {"dataset_id": "docs_qa_v1", "case_count": len(cases)}

    print("=== FieldForge Edge — configuration comparison (real, measured) ===")
    baseline = run_configuration("sparse_extractive", chunks, doc_id_to_filename, cases, False, False)
    report["sparse_extractive"] = baseline
    print(json.dumps(baseline, indent=2))

    if _ollama_reachable():
        hybrid = run_configuration("hybrid_generative", chunks, doc_id_to_filename, cases, True, True)
        report["hybrid_generative"] = hybrid
        print(json.dumps(hybrid, indent=2))

        print("\n=== Local model size comparison (fallback rate) ===")
        model_comparison = run_model_size_comparison(chunks)
        report["model_size_comparison"] = model_comparison
        for row in model_comparison:
            print(json.dumps(row, indent=2))
    else:
        report["hybrid_generative"] = "TBD (Ollama not reachable when this ran)"
        report["model_size_comparison"] = "TBD (Ollama not reachable when this ran)"
        print("\nOllama not reachable — hybrid/generative and model-size comparisons are TBD.")

    (REPORTS_DIR / "edge_comparison_v1_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {REPORTS_DIR / 'edge_comparison_v1_report.json'}")


if __name__ == "__main__":
    main()
