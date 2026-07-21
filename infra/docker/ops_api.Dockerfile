FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
COPY evals/scorers ./evals/scorers

RUN pip install --no-cache-dir -e .

ENV FIELDFORGE_OPS_DB_PATH=/data/fieldforge_ops.sqlite3
VOLUME ["/data"]

EXPOSE 8030

CMD ["uvicorn", "fieldforge_ops_api.main:app", "--host", "0.0.0.0", "--port", "8030"]
