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
```

## Before opening a PR

```bash
ruff check .
mypy packages services apps scripts evals
pytest -q
python scripts/run_eval.py
```

All four must pass. The guardrail eval must stay at 100% (see
`scripts/check_guardrail_gate.py`) — that's the one hard quality gate slice 1 enforces.

## Conventions

- No file over 500 lines; split by responsibility instead.
- Every new capability needs a test before it's considered done.
- Don't fabricate metrics. If you haven't measured it, write `TBD`.
- Update [docs/ROADMAP.md](docs/ROADMAP.md) when you complete or add a backlog item.
- Architectural changes get an ADR in `docs/adr/`.
