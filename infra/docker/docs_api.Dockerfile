FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
COPY evals/scorers ./evals/scorers

RUN pip install --no-cache-dir -e .

COPY data/samples ./data/samples

ENV FIELDFORGE_DB_PATH=/data/fieldforge_docs.sqlite3
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "fieldforge_docs_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
