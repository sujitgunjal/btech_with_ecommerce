# Person 3 — Backend + AI/RAG Handover

> **Project:** AI-Powered DevOps Incident Investigation System using RAG and LLMs  
> **Role:** Person 3 — Backend + AI/RAG  
> **Date:** 29 September 2026  
> **Last commit:** `b00454f person 3`

---

## 1. What Person 3 Is Responsible For

Person 3 implements the **AI investigation pipeline** — the system that takes a live DevOps incident, gathers real-time observability evidence from Prometheus/Loki/Jaeger (built by Person 2), retrieves similar past incidents from a vector database, sends everything to an LLM, and produces a structured Root Cause Analysis (RCA).

**Person 3 does NOT:**

- Build the frontend (Person 1).
- Build the observability collectors or evidence endpoints (Person 2).
- Implement autonomous remediation — the system only investigates and recommends.

---

## 2. Architecture Overview

```
User / Frontend
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI Backend  (backend/app/)                         │
│                                                          │
│  POST /incidents/{id}/investigate                        │
│       │                                                  │
│       ▼                                                  │
│  InvestigationService.start_investigation()              │
│       │                                                  │
│       ├── Steps 1-8: Telemetry Evidence Collection       │
│       │   └── TelemetryService → Prometheus, Loki,       │
│       │       Jaeger → Evidence rows stored in PostgreSQL │
│       │                                                  │
│       └── Steps 9-12: RAG + LLM Analysis (Person 3)     │
│           └── InvestigationEngine.investigate()           │
│               │                                          │
│               ├── 1. format_evidence_for_llm()           │
│               │      (groups evidence into logs/metrics/ │
│               │       traces text summaries)             │
│               │                                          │
│               ├── 2. build_semantic_query()               │
│               │      (builds natural-language search      │
│               │       query from incident + evidence)    │
│               │                                          │
│               ├── 3. IncidentRetriever.retrieve()         │
│               │      ┌─────────────────────┐             │
│               │      │ EmbeddingService     │             │
│               │      │ (all-MiniLM-L6-v2)  │             │
│               │      └────────┬────────────┘             │
│               │               ▼                          │
│               │      ┌─────────────────────┐             │
│               │      │ ChromaDB VectorStore │             │
│               │      │ (7 historical docs)  │             │
│               │      └─────────────────────┘             │
│               │                                          │
│               ├── 4. build_investigation_context()        │
│               │      (combines evidence + history)       │
│               │                                          │
│               ├── 5. build_system_prompt()                │
│               │    + build_user_prompt()                  │
│               │                                          │
│               ├── 6. LLMClient.generate_rca()             │
│               │      ┌─────────────────────┐             │
│               │      │ Ollama (local)       │             │
│               │      │ gemma4:31b-cloud     │             │
│               │      │ OpenAI-compatible API│             │
│               │      └─────────────────────┘             │
│               │                                          │
│               └── 7. Parse + Validate → RootCauseAnalysis │
│                      (Pydantic schema enforcement)       │
│                                                          │
│  Response: InvestigationResponse (JSON)                  │
│    ├── status, confidence, evidence_count                │
│    └── report: { root_cause, supporting_evidence,        │
│         affected_services, confidence, timeline,         │
│         alternative_explanations, recommended_actions,   │
│         relevant_historical_incidents }                  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. File Inventory — What Person 3 Created or Modified

### 3.1 New Files (Person 3 authored)

| File | Purpose |
|------|---------|
| `backend/app/investigation/__init__.py` | Package exports for the investigation pipeline |
| `backend/app/investigation/engine.py` | **Core orchestrator** — runs the full RAG + LLM pipeline |
| `backend/app/investigation/context.py` | `InvestigationContext` — combines evidence + history into one container |
| `backend/app/investigation/llm.py` | `LLMClient` — calls Ollama/OpenAI-compatible API, parses JSON response robustly |
| `backend/app/investigation/prompt.py` | System + user prompt templates with RCA JSON schema |
| `backend/app/rag/retriever.py` | `IncidentRetriever` — embeds query + searches ChromaDB |
| `backend/app/rag/documents.py` | Evidence preprocessor + semantic query generator |
| `backend/app/rag/__init__.py` | Package exports for RAG components |
| `backend/app/schemas/investigation.py` | `RootCauseAnalysis`, `InvestigationResponse`, `TimelineEntry`, `HistoricalIncidentRef` |
| `backend/scripts/test_components.py` | Local component test (no Docker needed) |
| `backend/scripts/test_investigation.py` | Full end-to-end API test with ground-truth evaluation |
| `backend/scripts/test_ollama.py` | Smoke test for Ollama connectivity |

### 3.2 Modified Files

| File | What Changed |
|------|-------------|
| `backend/app/config.py` | Added 6 settings: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `RAG_TOP_K`, `EMBEDDING_MODEL` |
| `backend/app/schemas/__init__.py` | Exported new schemas: `RootCauseAnalysis`, `TimelineEntry`, `HistoricalIncidentRef` |
| `backend/app/services/investigation_service.py` | Added steps 9-12: `_run_analysis()` method integrates `InvestigationEngine`, stores RCA as JSON in `report` column |
| `backend/app/routers/incidents.py` | Added `_parse_report()` helper to deserialize JSON from DB `Text` column; `import json` |
| `backend/app/routers/investigations.py` | Same JSON report parsing for the `GET /investigations/{id}` endpoint |
| `backend/Dockerfile` | Added `COPY data ./data` (makes ChromaDB index available inside the container) |
| `docker-compose.yml` | Added `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` to backend service env |
| `backend/requirements.txt` | Added `chromadb` and `openai` |
| `backend/.env.example` | Added Ollama/LLM and RAG configuration documentation |

### 3.3 Files from Prior Steps (NOT modified by Person 3)

These were already working before Person 3 started:

| File | Owner | Purpose |
|------|-------|---------|
| `backend/app/rag/embeddings.py` | Pre-existing (Person 3 prep) | `EmbeddingService` — Sentence Transformers `all-MiniLM-L6-v2`, 384-dim |
| `backend/app/rag/vector_store.py` | Pre-existing (Person 3 prep) | `VectorStore` — persistent ChromaDB at `backend/data/chroma/` |
| `backend/data/historical_incidents.json` | Pre-existing | 7 structured historical incidents (INC-001 to INC-007) |
| `backend/data/historical_incidents_embeddings.json` | Pre-existing | Pre-computed embeddings for all 7 incidents |
| `backend/data/chroma/` | Pre-existing | Persistent ChromaDB index with all 7 incidents indexed |
| `backend/scripts/build_historical_dataset.py` | Pre-existing | Converts scenario.json files → historical_incidents.json |
| `backend/scripts/embed_historical_incidents.py` | Pre-existing | Generates embeddings for historical incidents |
| `backend/scripts/index_historical_incidents.py` | Pre-existing | Indexes embedded incidents into ChromaDB |
| `backend/scripts/test_retrieval.py` | Pre-existing | Tests semantic retrieval from ChromaDB |
| `backend/scripts/test_embeddings.py` | Pre-existing | Tests the embedding service |
| `backend/app/services/evidence_service.py` | Person 2 | Unified evidence collection from Loki, Prometheus, Jaeger |
| `backend/app/services/telemetry_service.py` | Person 2 | Concurrent telemetry collection orchestration |
| `backend/app/collectors/` | Person 2 | Prometheus, Loki, Jaeger collector implementations |
| `backend/app/models/investigation.py` | Pre-existing | Investigation ORM model with `report` (Text) and `confidence` (Float) columns |

---

## 4. The 7 Historical Incidents (RAG Knowledge Base)

| ID | Type | Service | Severity | Root Cause (ground truth) |
|----|------|---------|----------|--------------------------|
| INC-001 | database_failure | postgres | CRITICAL | PostgreSQL container paused → dependent services fail |
| INC-002 | service_failure | product-service | HIGH | Product-service container paused → order-service 503s |
| INC-003 | high_latency | order-service | MEDIUM | Transport delay on order→product dependency path |
| INC-004 | cpu_spike | order-service | MEDIUM | CPU burn workload saturated the container |
| INC-005 | memory_spike | order-service | HIGH | In-container process allocated a large memory block |
| INC-006 | bad_deployment | order-service | HIGH | v1.3.0 deployment expected missing `available_stock` field |
| INC-007 | network_failure | order-service | HIGH | Packets dropped on order→product network path |

**Source files:** `incidents/*/scenario.json` (7 directories)  
**Converted to:** `backend/data/historical_incidents.json`  
**Embeddings:** `backend/data/historical_incidents_embeddings.json` (384-dim, all-MiniLM-L6-v2)  
**Indexed in:** `backend/data/chroma/` (ChromaDB persistent store, 7 documents)

---

## 5. LLM Configuration — Ollama + Gemma 4

| Setting | Value | Purpose |
|---------|-------|---------|
| `LLM_MODEL` | `gemma4:31b-cloud` | Ollama cloud-hosted Gemma 4 31B model |
| `LLM_API_KEY` | `ollama` | Dummy key (Ollama doesn't need real auth) |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | Ollama's OpenAI-compatible API (host machine, reachable from Docker) |
| `LLM_TEMPERATURE` | `0.2` | Low temperature for deterministic analysis |
| `LLM_MAX_TOKENS` | `3000` | Enough for full RCA JSON |

**How it connects:**  
The backend runs inside Docker. Ollama runs natively on the host (Windows). Docker reaches the host via `host.docker.internal`. Ollama exposes an OpenAI-compatible API at port `11434/v1`.

**For local testing (outside Docker):**  
Override `LLM_BASE_URL=http://localhost:11434/v1` in `.env` or environment.

**JSON handling quirk:**  
Gemma models sometimes wrap JSON in markdown code fences (` ```json ... ``` `). The `LLMClient._parse_response()` method handles this with three fallback extraction strategies:
1. Direct `json.loads()` parse
2. Regex extraction from ` ```json ... ``` ` code fences
3. Regex extraction of the first `{ ... }` block

---

## 6. Investigation Pipeline — Detailed Flow

When `POST /incidents/{id}/investigate` is called:

### Phase 1: Evidence Collection (Steps 1-8, pre-existing)

1. Create `Investigation` row in PostgreSQL (status: `pending`)
2. Set incident status → `investigating`
3. Set investigation status → `collecting`
4. Determine time window from incident `start_time` / `end_time`
5. Collect telemetry concurrently via `TelemetryService` from Prometheus, Loki, Jaeger
6. Store normalized evidence as `Evidence` rows in PostgreSQL
7. Record any collector errors as evidence rows (event_type: `collector_error`)
8. Log evidence collection outcome (complete / partial / failed)

### Phase 2: RAG + LLM Analysis (Steps 9-12, Person 3)

9. Set investigation status → `analyzing`
10. `InvestigationEngine.investigate()` is called:
    - **Format evidence:** Groups stored `Evidence` rows by source (loki/prometheus/jaeger), formats into human-readable text summaries with severity prioritization
    - **Generate semantic query:** Extracts incident title, description, key error messages, and event types into a natural-language search query
    - **Retrieve historical incidents:** Embeds the query with `all-MiniLM-L6-v2`, searches ChromaDB for top-3 similar historical incidents (similarity = `1 / (1 + L2_distance)`)
    - **Build context:** Combines current evidence summaries + historical incident references into an `InvestigationContext` object
    - **Build prompts:** System prompt (role, rules, JSON schema) + user prompt (incident details, evidence, historical context)
    - **Call LLM:** Sends to Ollama `gemma4:31b-cloud` via OpenAI-compatible API with `response_format={"type": "json_object"}`
    - **Parse + validate:** Extracts JSON from response (handles code fences), validates against `RootCauseAnalysis` Pydantic schema
11. Store the RCA JSON in `investigation.report` (Text column, JSON serialized) and confidence score in `investigation.confidence`
12. Set final status: `completed`, `completed_partial`, or `failed`

### Graceful Degradation

| Failure | Behavior |
|---------|----------|
| ChromaDB unavailable | Continues without historical context |
| All telemetry collectors fail | Sets status `failed`, reports no evidence |
| Some collectors fail | Sets status `completed_partial`, uses available evidence |
| Ollama / LLM unreachable | Returns fallback RCA with `confidence: 0.1` and suggestion to review manually |
| LLM returns invalid JSON | Falls back to evidence-only report |
| LLM not configured (`LLM_API_KEY` empty) | Returns fallback RCA |

---

## 7. RCA Output Schema

The LLM is instructed to return this JSON structure (validated by `RootCauseAnalysis` Pydantic model):

```json
{
  "root_cause": "PostgreSQL became unavailable after its container was paused, causing dependent services to fail with connection timeouts.",
  "supporting_evidence": [
    "Loki logs show OperationalError: connection refused from order-service at 09:00:15Z",
    "Prometheus HTTP 5xx counter for order-service increased from 0 to 47 during the window",
    "Jaeger traces contain failed database spans with timeout errors"
  ],
  "affected_services": ["postgres", "order-service", "product-service"],
  "confidence": 0.87,
  "timeline": [
    {"timestamp": "2026-09-21T09:00:00Z", "event": "PostgreSQL container became unresponsive"},
    {"timestamp": "2026-09-21T09:00:15Z", "event": "Dependent services begin logging connection errors"},
    {"timestamp": "2026-09-21T09:01:00Z", "event": "HTTP 5xx rate peaks across all dependent services"}
  ],
  "alternative_explanations": [
    "Network partition between application containers and postgres",
    "PostgreSQL connection pool exhaustion due to connection leak"
  ],
  "recommended_actions": [
    "Check postgres container status and health endpoint",
    "Unpause or restart the postgres container if paused",
    "Verify dependent service connection pools recover after postgres is restored",
    "Review container orchestration health checks for postgres"
  ],
  "relevant_historical_incidents": [
    {
      "incident_id": "INC-001",
      "incident_type": "database_failure",
      "similarity_score": 0.52,
      "relevance": "Same pattern of postgres unavailability causing cascading service failures"
    }
  ]
}
```

---

## 8. API Endpoints (Person 3 Relevant)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/incidents/{id}/investigate` | Triggers the full investigation pipeline (evidence collection + RAG + LLM). Returns `InvestigationResponse`. |
| `GET` | `/investigations/{id}` | Retrieves a completed investigation by ID (includes the RCA report). |
| `GET` | `/investigations/{id}/evidence` | Lists all evidence rows for an investigation. |
| `GET` | `/incidents/{id}/evidence` | Person 2's endpoint — returns unified logs/metrics/traces (not used in the pipeline directly, but demonstrates evidence collection). |

### InvestigationResponse Schema

```json
{
  "id": 1,
  "incident_id": 1,
  "status": "completed",
  "started_at": "2026-09-21T09:00:00Z",
  "completed_at": "2026-09-21T09:00:45Z",
  "report": { ... },
  "confidence": 0.87,
  "created_at": "2026-09-21T09:00:00Z",
  "evidence_count": 42
}
```

`status` values: `pending` → `collecting` → `analyzing` → `completed` | `completed_partial` | `failed`

---

## 9. Ground Truth Isolation

**Critical design principle:** The current incident's ground truth (`expected_root_cause` from `scenario.json`) is NEVER provided to the LLM.

- The `build_historical_dataset.py` script includes root causes in historical incident documents (this is correct — historical incidents are reference knowledge).
- The investigation pipeline only receives current **observability evidence** (logs, metrics, traces) and **historical context** (similar past incidents).
- The `find_incident_scenario()` function in `incident_service.py` explicitly excludes `expected_root_cause` — it only returns operational fields (`service`, `start_time`, `end_time`).
- Ground truth comparison happens only **after** the investigation, in `test_investigation.py`'s `evaluate_against_ground_truth()` function.

---

## 10. How to Run

### Prerequisites

- Docker Desktop running
- Ollama installed and running on the host machine
- `gemma4:31b-cloud` model pulled: `ollama pull gemma4:31b-cloud`

### Start Everything

```bash
# Start the Docker stack (all services except Ollama)
docker compose up -d --build

# Verify Ollama is running
ollama list
```

### Run Local Component Tests (no Docker needed)

```bash
cd backend
python -m scripts.test_components
```

Tests: schema validation, prompt generation, ChromaDB retrieval, LLM response parsing, context builder — all 8 tests should pass.

### Run Full End-to-End Test (requires Docker stack)

```bash
cd backend

# Test a single incident
python -m scripts.test_investigation --incident INC-001

# Test all 7 incidents
python -m scripts.test_investigation

# Dry run (create incidents without triggering investigation)
python -m scripts.test_investigation --dry-run
```

Results are saved to `backend/data/test_results.json`.

### Test Ollama Connectivity

```bash
cd backend
python -m scripts.test_ollama
```

---

## 11. Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `sentence-transformers` | — | `all-MiniLM-L6-v2` embedding model (384-dim) |
| `chromadb` | 1.5.9 | Persistent vector store for historical incidents |
| `openai` | 3.20.0 | OpenAI-compatible client (used to talk to Ollama) |
| `fastapi` | — | REST API framework |
| `sqlalchemy` | — | PostgreSQL ORM (Incident, Investigation, Evidence models) |
| `pydantic` / `pydantic-settings` | — | Schema validation + environment config |
| `httpx` | — | Async HTTP client for telemetry collectors |

---

## 12. Database Tables (Person 3 Relevant)

### `investigations` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `incident_id` | Integer FK → incidents.id | |
| `status` | String(20) | `pending` / `collecting` / `analyzing` / `completed` / `completed_partial` / `failed` |
| `started_at` | DateTime | When evidence collection began |
| `completed_at` | DateTime | When the full pipeline finished |
| `report` | Text | **JSON string** containing the full RCA (deserialized in the router) |
| `confidence` | Float | 0.0 – 1.0, extracted from the RCA |
| `created_at` | DateTime | Row creation timestamp |

### `evidence` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `incident_id` | Integer FK → incidents.id | |
| `source` | String(20) | `prometheus` / `loki` / `jaeger` |
| `service` | String(100) | e.g., `order-service` |
| `timestamp` | DateTime | Event timestamp |
| `event_type` | String(50) | e.g., `http_error`, `collector_error` |
| `severity` | String(20) | `info` / `warning` / `error` / `critical` |
| `content` | Text | The actual evidence content |
| `metadata` | JSON | Additional structured data |

---

## 13. Known Limitations / Future Work

1. **Embedding model is loaded on every retrieval call.** For production, it should be cached as a singleton or loaded at startup.
2. **LLM call is synchronous** (wrapped in an async method). For high concurrency, use the async OpenAI client.
3. **No caching** of LLM responses — repeated investigations for the same incident will re-call Ollama.
4. **ChromaDB data is baked into the Docker image** (via `COPY data ./data` in Dockerfile). For dynamic updates, use a volume mount instead.
5. **Only 7 historical incidents** in the knowledge base. The pipeline supports adding more via `build_historical_dataset.py` → `embed_historical_incidents.py` → `index_historical_incidents.py`.
6. **No streaming** — the full RCA is generated before responding. For large models, consider streaming the response.
7. **No autonomous remediation** — by design, the system only investigates and recommends manual actions.
