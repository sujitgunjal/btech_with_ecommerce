# AI-Powered Incident Investigation System

## Project guide

This repository contains the first working foundation of an AI-powered DevOps incident investigation platform.

The current implementation is intentionally phased. It includes three FastAPI microservices, PostgreSQL persistence, OpenTelemetry instrumentation, metrics, logs, distributed traces, a Grafana dashboard, and repeatable JSON validation output.

The later AI investigation layer is not included yet. RAG, embeddings, ChromaDB, LLM integration, automated incident summaries, and root-cause ranking remain future phases.

## Current implementation status

| Capability | Status | Description |
| --- | --- | --- |
| User Service | Complete | Creates and reads users through FastAPI. |
| Product Service | Complete | Creates and reads products and exposes stock information. |
| Order Service | Complete | Validates users and products, checks stock, and creates orders. |
| PostgreSQL persistence | Complete | Shared local database used by all three services. |
| OpenTelemetry | Complete | FastAPI, HTTPX, SQLAlchemy, metrics, and logs. |
| Prometheus | Complete | Stores and queries application metrics. |
| Loki | Complete | Stores application logs. |
| Jaeger | Complete | Stores distributed traces. |
| Grafana | Complete | Provides the pre-provisioned investigation dashboard. |
| JSON validation | Complete | Saves test results under output as JSON. |
| AI investigation engine | Planned | Not part of the current implementation. |

## What the system does

The main workflow is an order request:

1. A client submits user_id, product_id, and quantity.
2. Order Service calls User Service to validate the user.
3. Order Service calls Product Service to validate the product.
4. Order Service checks available stock.
5. Order Service saves the order in PostgreSQL.
6. OpenTelemetry records requests, downstream calls, database spans, metrics, and logs.
7. Prometheus, Loki, Jaeger, and Grafana expose evidence for investigation.

The current workflow checks stock but does not decrement it. Stock mutation is intentionally outside the current phase.

## Architecture

~~~mermaid
flowchart LR
    Client[Client or test script] --> Order[Order Service<br/>localhost:8003]
    Order --> User[User Service<br/>localhost:8001]
    Order --> Product[Product Service<br/>localhost:8002]
    User --> DB[(PostgreSQL)]
    Product --> DB
    Order --> DB

    Order -. OTLP .-> Collector[OpenTelemetry Collector]
    User -. OTLP .-> Collector
    Product -. OTLP .-> Collector

    Collector --> Metrics[Prometheus]
    Collector --> Logs[Loki]
    Collector --> Traces[Jaeger]
    Metrics --> Grafana[Grafana]
    Logs --> Grafana
    Traces --> Grafana
    CAdvisor[cAdvisor] --> Metrics
~~~

The OpenTelemetry Collector is the telemetry boundary. Services send OTLP telemetry to the Collector, which routes metrics to Prometheus, logs to Loki, and traces to Jaeger. Grafana queries all three backends.

## Repository layout

~~~text
.
├── docker-compose.yml
├── docs/
│   ├── observability.md
│   └── project-guide.md
├── observability/
│   ├── grafana/
│   ├── loki/
│   ├── otel/
│   ├── prometheus/
│   └── traffic-generator.py
├── output/
├── scripts/
│   └── save-test-results.ps1
└── services/
    ├── user-service/
    ├── product-service/
    └── order-service/
~~~


## Services and endpoints

| Component | Host endpoint | Container endpoint | Purpose |
| --- | --- | --- | --- |
| User Service | http://localhost:8001 | http://user-service:8000 | User CRUD foundation. |
| Product Service | http://localhost:8002 | http://product-service:8000 | Product and stock foundation. |
| Order Service | http://localhost:8003 | http://order-service:8000 | Cross-service order workflow. |
| PostgreSQL | localhost:5432 | postgres:5432 | Relational persistence. |
| OpenTelemetry Collector | localhost:4317 and localhost:4318 | otel-collector:4317 and otel-collector:4318 | OTLP telemetry intake. |
| Collector metrics | http://localhost:9464/metrics | http://otel-collector:9464/metrics | Prometheus scrape endpoint. |
| Prometheus | http://localhost:9090 | http://prometheus:9090 | Metrics storage and query API. |
| Grafana | http://localhost:3000 | http://grafana:3000 | Dashboard and exploration UI. |
| Loki | http://localhost:3100 | http://loki:3100 | Log storage and LogQL API. |
| Jaeger | http://localhost:16686 | http://jaeger:16686 | Distributed tracing UI and API. |
| cAdvisor | http://localhost:8080 | http://cadvisor:8080 | Container resource metrics. |

Health endpoints:

~~~text
GET http://localhost:8001/health
GET http://localhost:8002/health
GET http://localhost:8003/health
~~~

A healthy service returns JSON containing status: "healthy".

## Prerequisites

Install or make available:

- Docker Desktop with Docker Compose support.
- PowerShell 5.1 or PowerShell 7+ for the validation script.
- Git, if working with branches or pushing changes.

No local Python virtual environment is required. Service dependencies are installed inside Docker images.

## Start the project

Run from the repository root:

~~~powershell
docker compose config
docker compose up -d --build
docker compose ps
~~~

The expected base services are:

~~~text
cadvisor
postgres
grafana
jaeger
loki
order-service
otel-collector
product-service
prometheus
user-service
~~~

Allow the containers a few seconds to initialize before querying telemetry backends.

## Exercise the business flow

The examples below use fixture records already present in the local database. If the database is empty, create a user and product first.

Create a user:

~~~powershell
$userBody = '{"name":"Test User","email":"test-user@example.com"}'
Invoke-RestMethod -Method Post -Uri http://localhost:8001/users -ContentType application/json -Body $userBody
~~~

Create a product:

~~~powershell
$productBody = '{"name":"Incident Test Product","description":"Fixture product","price":10.50,"stock":100}'
Invoke-RestMethod -Method Post -Uri http://localhost:8002/products -ContentType application/json -Body $productBody
~~~

Create an order:

~~~powershell
$orderBody = '{"user_id":1,"product_id":1,"quantity":1}'
Invoke-RestMethod -Method Post -Uri http://localhost:8003/orders -ContentType application/json -Body $orderBody
~~~

Expected response shape:

~~~json
{
  "id": 12,
  "user_id": 1,
  "product_id": 1,
  "quantity": 1,
  "status": "created",
  "created_at": "2026-08-23T06:59:24.754945"
}
~~~

Read all orders or a single order:

~~~powershell
Invoke-RestMethod -Uri http://localhost:8003/orders
Invoke-RestMethod -Uri http://localhost:8003/orders/12
~~~

## Repeatable JSON validation

The validation script checks the running environment without adding application features. It records:

- Expected and running Compose services.
- Health responses from all three APIs.
- A real order creation request and response.
- Prometheus query availability and metric series counts.
- Loki order-success log entries.
- Jaeger services and a distributed POST /orders trace.
- Grafana health and the provisioned dashboard.

Run normal validation:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\save-test-results.ps1
~~~

The result is written to output/project-test-results.json. The console output looks like:

~~~text
Saved test results to ...\output\project-test-results.json
Overall status: PASS
~~~

The JSON structure is:

~~~json
{
  "overall_status": "PASS",
  "failed_tests": [],
  "tests": {
    "services": { "status": "PASS" },
    "health": { "status": "PASS" },
    "order_creation": { "status": "PASS" },
    "prometheus": { "status": "PASS" },
    "loki": { "status": "PASS" },
    "jaeger": { "status": "PASS" },
    "grafana": { "status": "PASS" }
  }
}
~~~

When a check fails, the same structure reports FAIL and lists the failed groups:

~~~json
{
  "overall_status": "FAIL",
  "failed_tests": ["services", "health", "order_creation"]
}
~~~

Use OutputFile to preserve a separate run:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\save-test-results.ps1 -OutputFile project-failure-test-results.json
~~~

## Optional traffic generator

The traffic generator continuously calls the existing APIs and creates telemetry for dashboards:

~~~powershell
docker compose --profile traffic up -d traffic-generator
docker compose logs -f traffic-generator
docker compose stop traffic-generator
~~~

The traffic generator is optional. The normal Compose stack does not require it.

## Observability workflow

### Metrics in Prometheus

| Metric | Type | Meaning |
| --- | --- | --- |
| app_http_request_count_total | Counter | Total HTTP request count. |
| app_http_error_count_total | Counter | HTTP 5xx error count. |
| app_http_request_duration_seconds | Histogram | Request-duration distribution. |

Example PromQL:

~~~promql
sum by (service_name) (rate(app_http_request_count_total[1m]))
sum by (service_name) (rate(app_http_error_count_total[1m]))
histogram_quantile(0.95, sum by (le, service_name) (rate(app_http_request_duration_seconds_bucket[5m])))
~~~

Check target health at http://localhost:9090/targets. The otel-collector and cadvisor targets should be UP.

### Logs in Loki

~~~logql
{service_name="order-service"}
{service_name="order-service"} | level = "ERROR"
{service_name="order-service"} |= "Order created successfully"
{service_name="order-service"} |= "User service unavailable"
~~~

Loki readiness is available at http://localhost:3100/ready.

### Distributed traces in Jaeger

An order trace normally contains order-service, user-service, product-service, HTTPX, and SQLAlchemy spans. Open http://localhost:16686, select order-service, and search for POST /orders.

~~~text
GET http://localhost:16686/api/services
GET http://localhost:16686/api/traces?service=order-service&operation=POST%20%2Forders
~~~

### Grafana dashboard

Open http://localhost:3000 and use the dashboard named:

~~~text
AI Incident Investigation - Observability
~~~

Dashboard panels:

1. Request rate.
2. 5xx error rate.
3. P95 request latency.
4. Container CPU usage.
5. Container memory usage.
6. Order Service errors from Loki.

The local development credentials are admin / admin. Replace them before deployment.

## Controlled incident validation

User Service failure:

~~~powershell
docker compose stop user-service
Invoke-RestMethod -Method Post -Uri http://localhost:8003/orders -ContentType application/json -Body '{"user_id":1,"product_id":1,"quantity":1}'
docker compose start user-service
~~~

Expected result: Order Service returns 503 with User service unavailable. Prometheus shows increased errors, Loki contains the error log, and Jaeger contains the failed downstream span.

Product Service failure:

~~~powershell
docker compose stop product-service
docker compose start product-service
~~~

Expected result: Order Service returns 503 with Product service unavailable while Product Service is unavailable.

Database failure:

~~~powershell
docker compose stop postgres
docker compose start postgres
~~~

Expected result: database connection errors appear in service logs and SQL traces. Allow PostgreSQL time to become healthy before sending recovery traffic.

The current branch does not include an artificial latency switch. Latency investigation is supported by the request-duration histogram and Jaeger span timing, but latency injection is intentionally not part of this implementation.

## Failure response behavior

| Condition | Expected response |
| --- | --- |
| Unknown user during order creation | 404 User not found |
| Unknown product during order creation | 404 Product not found |
| Requested quantity exceeds product stock | 400 Insufficient stock |
| User Service cannot be reached | 503 User service unavailable |
| Product Service cannot be reached | 503 Product service unavailable |
| Unexpected downstream response | 502 Unexpected response from the relevant service |
| Invalid request body | FastAPI/Pydantic validation error, normally 422. |

## Configuration

~~~text
USER_SERVICE_URL=http://user-service:8000
PRODUCT_SERVICE_URL=http://product-service:8000
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
DEPLOYMENT_ENVIRONMENT=development
~~~

Inside Docker, use service DNS names rather than localhost. Telemetry is configured in each service's app/telemetry.py.

## Troubleshooting

Containers do not start:

~~~powershell
docker compose config
docker compose ps
docker compose logs --tail=100
~~~

Collector keeps restarting:

~~~powershell
docker compose logs otel-collector
~~~

Check observability/otel/otel-collector-config.yaml and confirm Loki and Jaeger are running.

No metrics appear: generate an API request, wait a few seconds, then check http://localhost:9464/metrics and http://localhost:9090/targets.

No logs appear in Loki: confirm http://localhost:3100/ready, generate a request, wait for the Collector batch interval, and query Loki again.

No traces appear in Jaeger: confirm the Collector and Jaeger are running, generate a new POST /orders request, and search for order-service.

Services cannot reach each other: use user-service, product-service, postgres, and otel-collector as container hostnames. Do not use localhost for container-to-container calls.

## Stopping and cleaning up

~~~powershell
docker compose stop
docker compose down
~~~

Use docker compose down -v only when deleting local database and telemetry history is intentional.

## Scope boundaries and next phase

Not included in this phase:

- RAG pipeline.
- Embedding generation.
- ChromaDB or another vector database.
- LLM provider integration.
- Automated incident summaries.
- Root-cause ranking or remediation recommendations.
- Production authentication, secrets management, TLS, and multi-tenant isolation.
- Artificial latency injection.

The observability stack provides the evidence foundation for those future capabilities. A later investigation service can query Prometheus, Loki, and Jaeger, normalize records around a time window, correlate using trace IDs, and pass the evidence to an analysis layer.

## Related documentation

- [Observability runbook](./observability.md)
- [OpenTelemetry Collector configuration](../observability/otel/otel-collector-config.yaml)
- [Grafana dashboard definition](../observability/grafana/dashboards/incident-investigation.json)
- [JSON test output](../output/project-test-results.json)
- [Failure test output](../output/project-failure-test-results.json)
