# Architecture — FieldForge Docs (Slice 1)

Status: **Implemented** sections describe what runs today. **Planned** sections describe the
target architecture for milestone M2+ and are not yet built.

## Component diagram (Implemented, slice 1)

```mermaid
flowchart LR
    subgraph Client
        CLI[HTTP client / pytest TestClient]
    end

    subgraph API["apps/docs_api (FastAPI)"]
        H[/health/]
        D[/documents/]
        Q[/query/]
        MW[Correlation-ID + JSON log middleware]
    end

    subgraph Ingestion["services/ingestion"]
        EX[Text/PDF extractor]
        CH[Fixed-token chunker]
    end

    subgraph Guardrails["services/guardrails"]
        IR[Input rails: file type/size, PII/secret regex]
        RR[Retrieval rails: prompt-injection pattern scan]
        OR[Output rails: citation validation, refusal-on-no-evidence]
    end

    subgraph Retrieval["services/retrieval"]
        BM[BM25 sparse index]
        EMB["Embedding adapter (NullEmbeddingAdapter default)"]
        FUS[RRF fusion — no-op when dense absent]
    end

    subgraph Answer["Answer generation"]
        FAKE[Deterministic extractive adapter]
    end

    subgraph Store["In-process store"]
        DOCSTORE[(Document/Chunk store — SQLite)]
    end

    CLI --> MW --> D --> IR --> EX --> CH --> DOCSTORE
    CLI --> MW --> Q --> RR
    Q --> BM
    Q --> EMB --> FUS
    BM --> FUS
    FUS --> OR --> FAKE --> OR
    DOCSTORE --> BM
```

## Component diagram (Planned, M2+)

```mermaid
flowchart LR
    subgraph Planned["Planned additions"]
        OCR[Tesseract OCR fallback]
        QD[(Qdrant dense index)]
        RERANK[Cross-encoder reranker]
        LLM["Live LLM adapter (OpenAI-compatible / Ollama)"]
        WEB[Next.js web UI]
        AUTH[RBAC — Viewer/Operator/Engineer/Safety Manager/Admin]
        OTEL[OpenTelemetry traces]
        PG[(PostgreSQL)]
    end
```

## Request sequence — `/query` (Implemented)

```mermaid
sequenceDiagram
    participant C as Client
    participant API as docs_api
    participant GR as Guardrails
    participant R as Retrieval (BM25)
    participant A as Extractive Answer Adapter

    C->>API: POST /query {question}
    API->>API: assign correlation_id, log request
    API->>GR: input rail (size/lang/PII checks on question)
    GR-->>API: pass / block
    API->>R: retrieve(question, k)
    R-->>API: RetrievalResult[] with scores + provenance
    API->>GR: retrieval rail (injection-pattern scan on chunks)
    GR-->>API: filtered RetrievalResult[]
    alt evidence sufficient
        API->>A: generate(question, chunks)
        A-->>API: answer + citations
        API->>GR: output rail (citation validation)
        GR-->>API: pass
        API-->>C: 200 {answer, citations, trace_id}
    else evidence insufficient
        API-->>C: 200 {answer: refusal, reason, trace_id}
    end
```

## Trust boundaries

```mermaid
flowchart TB
    subgraph Untrusted
        UP[Uploaded document content]
        UQ[User query text]
    end
    subgraph Trusted["Trusted process boundary"]
        ING[Ingestion pipeline]
        IDX[Index / store]
        GEN[Answer generator]
    end
    UP -- "quarantine + validate before parse" --> ING
    UQ -- "input rail before use" --> GEN
    ING -- "chunks scanned for embedded instructions" --> GEN
```

Retrieved chunk text is **data**, never instructions — the retrieval rail strips/flags
imperative-toward-the-model patterns found inside document content before it reaches the
answer step. See [threat model](../threat-model/THREAT_MODEL.md).

## Data model (slice 1, implemented subset)

See [packages/contracts](../../packages/contracts/fieldforge_contracts) for the authoritative
Pydantic definitions. Implemented now: `Document`, `DocumentPage`, `Chunk`, `RetrievalResult`,
`Citation`, `EvaluationCase`, `EvaluationResult`. Planned (Copilot/Mesh milestones): `Device`,
`Sensor`, `TelemetryPoint`, `Alert`, `Incident`, `Evidence`, `AgentTask`, `AgentMessage`,
`ToolRequest`, `ToolResult`, `ApprovalRequest`, `ApprovalDecision`, `MaintenanceTicket`,
`ModelRun`, `TraceReference`.

## Why BM25-first instead of dense-first

Dense retrieval needs an embedding provider (API key or a local model). Slice 1's non-functional
requirement is "runs offline with zero external services." BM25 is deterministic, dependency-light
(`rank_bm25`), and gives a real, measurable baseline immediately. The `EmbeddingAdapter` interface
is defined so a dense adapter (Ollama-served embedding model, or a cloud provider) can be added
without changing the retrieval or API layer — see `services/retrieval/fieldforge_retrieval/embedding.py`.
This is the same graceful-degradation posture the suite requires end-to-end: prefer a real, weaker
answer over a fabricated strong one.
