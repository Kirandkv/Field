"""Runs the FieldForge Docs slice-1 evaluation suite and writes a real, measured report.

No metric here is invented — every number is computed against the actual pipeline
(services/ingestion, services/retrieval, services/guardrails, the extractive answer
adapter) on the corpus in data/samples/. See docs/EVALUATION_METHODOLOGY.md.

Usage:
    python scripts/run_eval.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fieldforge_contracts import Document, EvaluationCase  # noqa: E402
from fieldforge_guardrails import (  # noqa: E402
    scan_query_text,
    scan_retrieved_chunks,
    validate_citations,
    validate_upload,
)
from fieldforge_ingestion import chunk_pages, extract_pages  # noqa: E402
from fieldforge_model_adapters import ExtractiveAnswerAdapter  # noqa: E402
from fieldforge_retrieval import BM25Index  # noqa: E402
from scorers.retrieval_scorer import (  # noqa: E402
    CaseResult,
    citation_correctness,
    latency_percentile,
    mean_reciprocal_rank,
    recall_at_k,
    refusal_accuracy,
    retrieved_filenames,
)

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
QA_DATASET = REPO_ROOT / "evals" / "datasets" / "docs_qa_v1.jsonl"
GUARDRAIL_DATASET = REPO_ROOT / "evals" / "datasets" / "guardrails_docs_v1.jsonl"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"
DATASET_VERSION = "v1"


def build_index() -> tuple[BM25Index, dict[str, str], dict[str, list]]:
    index = BM25Index()
    all_chunks = []
    doc_id_to_filename: dict[str, str] = {}
    chunks_by_doc: dict[str, list] = {}
    for path in sorted(SAMPLES_DIR.glob("*.md")):
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        doc = Document(id=sha256, filename=path.name, content_type="text/markdown", sha256=sha256)
        pages = extract_pages(doc.id, "text/markdown", raw)
        chunks = chunk_pages(pages)
        all_chunks.extend(chunks)
        doc_id_to_filename[doc.id] = doc.filename
        chunks_by_doc[doc.filename] = chunks
    index.build(all_chunks)
    return index, doc_id_to_filename, chunks_by_doc


def load_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def run_qa_eval(index: BM25Index, doc_id_to_filename: dict[str, str]) -> dict:
    cases = [EvaluationCase(**row) for row in load_jsonl(QA_DATASET)]
    adapter = ExtractiveAnswerAdapter()
    results: list[CaseResult] = []

    for case in cases:
        start = time.perf_counter()
        input_decisions = scan_query_text(case.question)
        clean_results: list = []
        if not any(not d.passed for d in input_decisions):
            raw_results = index.search(case.question, k=5)
            clean_results, _ = scan_retrieved_chunks(raw_results)
        generated = adapter.generate(case.question, clean_results)
        citations_valid = True
        if not generated.refused:
            valid_ids = {r.chunk.id for r in clean_results}
            citations_valid = validate_citations(generated.citations, valid_ids).passed
        latency_ms = (time.perf_counter() - start) * 1000

        results.append(
            CaseResult(
                case_id=case.id,
                gold_filenames=set(case.gold_document_ids),
                retrieved_filenames=retrieved_filenames(clean_results, doc_id_to_filename),
                expect_refusal=case.expect_refusal,
                actual_refused=generated.refused,
                citations_valid=citations_valid,
                latency_ms=latency_ms,
            )
        )

    return {
        "dataset_id": "docs_qa_v1",
        "dataset_version": DATASET_VERSION,
        "case_count": len(results),
        "recall_at_5": round(recall_at_k(results), 3),
        "mrr": round(mean_reciprocal_rank(results), 3),
        "refusal_accuracy": round(refusal_accuracy(results), 3),
        "citation_correctness": round(citation_correctness(results), 3),
        "latency_ms_p50": round(latency_percentile(results, 50), 3),
        "latency_ms_p95": round(latency_percentile(results, 95), 3),
        "limitations": (
            "Small corpus (7 documents); recall/MRR are indicative for this project's "
            "own regression testing, not representative of production-scale corpora. "
            "citation_correctness here is the automated resolve-check only (does the "
            "cited chunk id exist), not a semantic-support judgment — see "
            "docs/EVALUATION_METHODOLOGY.md."
        ),
    }


def run_guardrail_eval(chunks_by_doc: dict[str, list]) -> dict:
    rows = load_jsonl(GUARDRAIL_DATASET)
    correct = 0
    detail = []
    for row in rows:
        rtype = row["type"]
        expect_blocked = row["expect_blocked"]
        if rtype in ("query_injection", "query_pii"):
            decisions = scan_query_text(row["input"])
            blocked = any(not d.passed for d in decisions)
        elif rtype == "upload_filename":
            decision = validate_upload(row["input"], "text/plain", 100)
            blocked = not decision.passed
        elif rtype == "corpus_embedded_instruction":
            chunks = chunks_by_doc.get(row["input"], [])
            from fieldforge_contracts import RetrievalResult

            real_results = [
                RetrievalResult(chunk=c, score=1.0, rank=i + 1, retriever="bm25")
                for i, c in enumerate(chunks)
            ]
            clean, _ = scan_retrieved_chunks(real_results)
            blocked = len(clean) < len(real_results)
        else:
            raise ValueError(f"unknown guardrail case type: {rtype}")

        ok = blocked == expect_blocked
        correct += int(ok)
        detail.append(
            {
                "id": row["id"],
                "type": rtype,
                "expected_blocked": expect_blocked,
                "actual_blocked": blocked,
                "pass": ok,
            }
        )

    return {
        "dataset_id": "guardrails_docs_v1",
        "dataset_version": DATASET_VERSION,
        "case_count": len(rows),
        "accuracy": round(correct / len(rows), 3) if rows else 0.0,
        "detail": detail,
    }


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    index, doc_id_to_filename, chunks_by_doc = build_index()

    qa_report = run_qa_eval(index, doc_id_to_filename)
    guardrail_report = run_guardrail_eval(chunks_by_doc)

    (REPORTS_DIR / "docs_qa_v1_report.json").write_text(
        json.dumps(qa_report, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "guardrails_docs_v1_report.json").write_text(
        json.dumps(guardrail_report, indent=2), encoding="utf-8"
    )

    print("=== FieldForge Docs — Slice 1 Evaluation ===")
    print(f"Indexed chunks: {index.size}")
    print("\n-- Retrieval / Answer (docs_qa_v1) --")
    for k, v in qa_report.items():
        if k != "limitations":
            print(f"{k}: {v}")
    print("\n-- Guardrails (guardrails_docs_v1) --")
    print(f"accuracy: {guardrail_report['accuracy']} ({guardrail_report['case_count']} cases)")
    for d in guardrail_report["detail"]:
        status = "PASS" if d["pass"] else "FAIL"
        print(f"  [{status}] {d['id']} ({d['type']})")

    if guardrail_report["accuracy"] < 1.0:
        print("\nWARNING: guardrail eval did not achieve 100% — see detail above.")


if __name__ == "__main__":
    main()
