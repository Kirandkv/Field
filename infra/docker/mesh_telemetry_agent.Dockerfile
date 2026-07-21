FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
COPY evals/scorers ./evals/scorers

RUN pip install --no-cache-dir -e .

COPY data/samples/telemetry ./data/samples/telemetry

ENV FIELDFORGE_TELEMETRY_AGENT_URL=http://mesh_telemetry_agent:8021
ENV FIELDFORGE_MESH_AGENT_TOKEN=dev-mesh-token

EXPOSE 8021

CMD ["uvicorn", "fieldforge_mesh_telemetry_agent.main:app", "--host", "0.0.0.0", "--port", "8021"]
