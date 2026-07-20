.PHONY: install lint typecheck test eval check docker-build run run-copilot

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
	python data/generators/generate_telemetry.py
	python scripts/run_eval.py
	python scripts/check_guardrail_gate.py
	python scripts/run_copilot_eval.py

check: lint typecheck test eval

docker-build:
	docker build -f infra/docker/docs_api.Dockerfile -t fieldforge-docs-api:local .
	docker build -f infra/docker/copilot_api.Dockerfile -t fieldforge-copilot-api:local .

run:
	uvicorn fieldforge_docs_api.main:app --reload --port 8000

run-copilot:
	uvicorn fieldforge_copilot_api.main:app --reload --port 8010
