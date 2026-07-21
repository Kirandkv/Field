.PHONY: install lint typecheck test eval check docker-build run run-copilot run-mesh-analyst run-mesh-commander

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
	python scripts/run_mesh_eval.py

check: lint typecheck test eval

docker-build:
	docker build -f infra/docker/docs_api.Dockerfile -t fieldforge-docs-api:local .
	docker build -f infra/docker/copilot_api.Dockerfile -t fieldforge-copilot-api:local .
	docker build -f infra/docker/mesh_telemetry_agent.Dockerfile -t fieldforge-mesh-telemetry-agent:local .
	docker build -f infra/docker/mesh_commander.Dockerfile -t fieldforge-mesh-commander:local .

run:
	uvicorn fieldforge_docs_api.main:app --reload --port 8000

run-copilot:
	uvicorn fieldforge_copilot_api.main:app --reload --port 8010

run-mesh-analyst:
	uvicorn fieldforge_mesh_telemetry_agent.main:app --reload --port 8021

run-mesh-commander:
	uvicorn fieldforge_mesh_commander.main:app --reload --port 8022
