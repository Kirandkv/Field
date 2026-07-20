FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
COPY evals/scorers ./evals/scorers

RUN pip install --no-cache-dir -e .

COPY data/samples/telemetry ./data/samples/telemetry

ENV FIELDFORGE_COPILOT_DB_PATH=/data/fieldforge_copilot.sqlite3
ENV FIELDFORGE_DOCS_API_URL=http://docs_api:8000
VOLUME ["/data"]

EXPOSE 8010

CMD ["uvicorn", "fieldforge_copilot_api.main:app", "--host", "0.0.0.0", "--port", "8010"]
