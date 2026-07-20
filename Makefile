.PHONY: install lint typecheck test eval check docker-build run

install:
	pip install -e ".[dev]"

lint:
	ruff check .

typecheck:
	mypy packages services apps scripts evals

test:
	pytest -q

eval:
	python data/generators/generate_corpus.py
	python scripts/run_eval.py
	python scripts/check_guardrail_gate.py

check: lint typecheck test eval

docker-build:
	docker build -f infra/docker/docs_api.Dockerfile -t fieldforge-docs-api:local .

run:
	uvicorn fieldforge_docs_api.main:app --reload --port 8000
