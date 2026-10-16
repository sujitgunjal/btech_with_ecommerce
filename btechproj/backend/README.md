# Incident Investigation Backend

FastAPI backend for the **AI-Powered DevOps Incident Investigation System**.

This service provides incident management APIs, telemetry collection
from Prometheus / Loki / Jaeger, and normalized evidence storage in
PostgreSQL.

## Quick Start

```bash
# From the repository root
docker compose up -d --build
```

The backend will be available at **http://localhost:8010**.

| Service           | URL                          |
|-------------------|------------------------------|
| Backend API       | http://localhost:8010        |
| Swagger UI        | http://localhost:8010/docs   |
| ReDoc             | http://localhost:8010/redoc  |
| User Service      | http://localhost:8001        |
| Product Service   | http://localhost:8002        |
| Order Service     | http://localhost:8003        |

## Environment Variables

| Variable           | Default                                                          | Description                |
|--------------------|------------------------------------------------------------------|----------------------------|
| `DATABASE_URL`     | `postgresql+psycopg://postgres:1235@postgres:5432/devops_db`     | PostgreSQL connection URI  |
| `PROMETHEUS_URL`   | `http://prometheus:9090`                                         | Prometheus base URL        |
| `LOKI_URL`         | `http://loki:3100`                                               | Loki base URL              |
| `JAEGER_URL`       | `http://jaeger:16686`                                            | Jaeger query base URL      |
| `COLLECTOR_TIMEOUT`| `10.0`                                                           | HTTP timeout for collectors|

Copy `.env.example` to `.env` and edit as needed.

## API Endpoints

### Health

| Method | Path            | Description                    |
|--------|-----------------|--------------------------------|
| GET    | `/health`       | Combined health check          |
| GET    | `/health/live`  | Liveness probe                 |
| GET    | `/health/ready` | Readiness probe (checks DB)    |

### Incidents

| Method | Path                              | Description                |
|--------|-----------------------------------|----------------------------|
| POST   | `/incidents`                      | Create a new incident      |
| GET    | `/incidents`                      | List incidents (filterable)|
| GET    | `/incidents/{id}`                 | Get incident by ID         |
| PATCH  | `/incidents/{id}`                 | Update incident fields     |
| POST   | `/incidents/{id}/resolve`         | Mark incident as resolved  |
| POST   | `/incidents/{id}/investigate`     | Trigger investigation      |
| GET    | `/incidents/{id}/evidence`        | List incident evidence     |

### Investigations

| Method | Path                              | Description                |
|--------|-----------------------------------|----------------------------|
| GET    | `/investigations/{id}`            | Get investigation details  |
| GET    | `/investigations/{id}/evidence`   | List investigation evidence|

## Incident Lifecycle

```
created → investigating → resolved
                        → failed
```

## Investigation Status

| Status              | Meaning                                       |
|---------------------|-----------------------------------------------|
| `pending`           | Investigation created, not yet started         |
| `collecting`        | Telemetry collection in progress               |
| `completed`         | All collectors succeeded                       |
| `completed_partial` | Some collectors succeeded, some failed         |
| `failed`            | All collectors failed                          |

## Testing

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Unit tests use an in-memory SQLite database — no external services required.

## Project Structure

```
backend/
├── app/
│   ├── main.py            # FastAPI application entry point
│   ├── config.py          # Environment-based settings
│   ├── database.py        # SQLAlchemy engine and session
│   ├── models/            # ORM models (Incident, Investigation, Evidence)
│   ├── schemas/           # Pydantic request/response schemas
│   ├── routers/           # API route handlers
│   ├── services/          # Business logic layer
│   └── collectors/        # Telemetry collectors (Prometheus, Loki, Jaeger)
├── tests/                 # pytest test suite
├── Dockerfile
├── requirements.txt
├── .env.example
└── .dockerignore
```

## Future Extensions

The backend is designed so the following can be added without rewriting:

- Embedding generation for evidence
- Vector database storage (ChromaDB / Qdrant)
- RAG-based context retrieval
- LLM-powered root cause analysis
- Investigation report generation
