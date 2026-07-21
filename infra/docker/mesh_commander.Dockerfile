FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
COPY evals/scorers ./evals/scorers

RUN pip install --no-cache-dir -e .

ENV FIELDFORGE_MESH_COMMANDER_DB_PATH=/data/fieldforge_mesh_commander.sqlite3
ENV FIELDFORGE_MESH_AGENT_TOKEN=dev-mesh-token
VOLUME ["/data"]

EXPOSE 8022

CMD ["uvicorn", "fieldforge_mesh_commander.main:app", "--host", "0.0.0.0", "--port", "8022"]
