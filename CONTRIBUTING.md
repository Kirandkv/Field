# Contributing

This repo currently has a single maintainer and is built incrementally, one vertical
slice at a time — see [docs/ROADMAP.md](docs/ROADMAP.md) for what's implemented vs.
planned.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
python data/generators/generate_corpus.py
python data/generators/generate_telemetry.py
```

## Before opening a PR

```bash
ruff check .
mypy packages services apps scripts evals
pytest -q
python scripts/run_eval.py
python scripts/run_copilot_eval.py
python scripts/run_mesh_eval.py
```

All six must pass. The Docs guardrail eval must stay at 100% (see
`scripts/check_guardrail_gate.py`); the Copilot and Mesh scenario suites must stay at
100% (both exit non-zero on any failing scenario) — those are the three hard quality
gates slice 1 enforces directly. FieldForge Ops' own gate logic is covered by
`pytest` (`tests/unit/test_gate.py`, `tests/integration/test_ops_regression_demo.py`)
rather than a standalone script, since Ops evaluates the *other* three products'
reports rather than running its own domain eval.

FieldForge Edge's tests (`tests/unit/test_ollama_adapters.py`,
`tests/integration/test_docs_api_edge_mode.py`) are included in `pytest -q` above and
run everywhere — the ones that need a real local model call skip (not fail) when
Ollama isn't reachable, so CI stays green without Ollama installed. If you have Ollama
running locally with `nomic-embed-text` and a chat model pulled, those tests run for
real; `python scripts/run_edge_comparison_eval.py` reproduces the measured comparison
numbers in `evals/reports/edge_comparison_v1_report.json`.

## Conventions

- No file over 500 lines; split by responsibility instead.
- Every new capability needs a test before it's considered done.
- Don't fabricate metrics. If you haven't measured it, write `TBD`.
- Update [docs/ROADMAP.md](docs/ROADMAP.md) when you complete or add a backlog item.
- Architectural changes get an ADR in `docs/adr/`.
