# AI-Powered Incident Investigation System

A containerized microservice foundation for collecting the evidence needed to investigate DevOps incidents.

The current project includes:

- FastAPI User, Product, and Order services.
- PostgreSQL persistence.
- OpenTelemetry traces, metrics, and logs.
- Prometheus metrics storage.
- Loki log storage.
- Jaeger distributed tracing.
- Grafana dashboards.
- cAdvisor container-resource metrics.
- A repeatable PowerShell validation script that saves JSON results.

## Current status

The application and observability foundation is implemented and tested. The AI investigation layer is intentionally not included yet. RAG, embeddings, ChromaDB, LLM integration, automated summaries, and root-cause ranking are planned for later phases.

## Quick start

~~~powershell
docker compose config
docker compose up -d --build
docker compose ps
~~~

Check the API health endpoints:

~~~text
http://localhost:8001/health
http://localhost:8002/health
http://localhost:8003/health
~~~

Create an order using the existing fixture records:

~~~powershell
$body = '{"user_id":1,"product_id":1,"quantity":1}'
Invoke-RestMethod -Method Post -Uri http://localhost:8003/orders -ContentType application/json -Body $body
~~~

## Observability URLs

| Tool | URL | Purpose |
| --- | --- | --- |
| Prometheus | http://localhost:9090 | Metrics queries and target health. |
| Grafana | http://localhost:3000 | Incident dashboard and exploration. |
| Loki | http://localhost:3100 | Log query API and readiness. |
| Jaeger | http://localhost:16686 | Distributed trace search. |
| Collector metrics | http://localhost:9464/metrics | Exported application metrics. |
| cAdvisor | http://localhost:8080 | Container resource metrics. |

The provisioned Grafana dashboard is named **AI Incident Investigation - Observability**. Local Grafana credentials are admin / admin for development only.

## Save validation results

Run the repeatable validation:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\save-test-results.ps1
~~~

The result is saved to:

~~~text
output/project-test-results.json
~~~

The JSON includes service status, API health, order creation, Prometheus, Loki, Jaeger, and Grafana results. A successful run reports overall_status as PASS. A failed run reports overall_status as FAIL and lists failed_tests.

## Documentation

- [Detailed project guide](docs/project-guide.md)
- [Observability runbook](docs/observability.md)
- [OpenTelemetry Collector configuration](observability/otel/otel-collector-config.yaml)
- [Grafana dashboard definition](observability/grafana/dashboards/incident-investigation.json)
- [Latest successful JSON test output](output/project-test-results.json)
- [Captured controlled failure output](output/project-failure-test-results.json)

## Stop the environment

~~~powershell
docker compose stop
~~~

Use docker compose down to remove containers while retaining named volumes. Use docker compose down -v only when intentionally deleting local database and telemetry history.
