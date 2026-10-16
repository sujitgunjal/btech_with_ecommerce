# Phase 1B Observability Runbook

This phase adds OpenTelemetry instrumentation and a reproducible telemetry stack to the existing FastAPI services. It stops at the telemetry foundation: RAG, embeddings, ChromaDB, LLM integration, and the AI investigation engine are intentionally out of scope.

## Architecture

```text
FastAPI services
  ├─ traces: FastAPI + HTTPX + SQLAlchemy instrumentation
  ├─ metrics: OpenTelemetry SDK + request middleware
  └─ logs: existing Python logging through OpenTelemetry LoggingHandler
          │ OTLP/gRPC
          ▼
OpenTelemetry Collector
  ├─ metrics ──► Prometheus ──► Grafana
  ├─ logs ────► Loki ─────────► Grafana
  └─ traces ──► Jaeger ───────► Grafana
```

The Collector is the boundary between application instrumentation and storage backends. The future data-collection layer should query Prometheus, Loki, and Jaeger directly; Grafana is for human visualization.

## Services and endpoints

| Service | Host endpoint | Container endpoint |
| --- | --- | --- |
| User Service | http://localhost:8001 | http://user-service:8000 |
| Product Service | http://localhost:8002 | http://product-service:8000 |
| Order Service | http://localhost:8003 | http://order-service:8000 |
| PostgreSQL | localhost:5432 | postgres:5432 |
| OpenTelemetry Collector OTLP/gRPC | localhost:4317 | otel-collector:4317 |
| OpenTelemetry Collector OTLP/HTTP | localhost:4318 | otel-collector:4318 |
| Collector Prometheus exporter | http://localhost:9464/metrics | http://otel-collector:9464/metrics |
| Prometheus | http://localhost:9090 | http://prometheus:9090 |
| Grafana | http://localhost:3000 | http://grafana:3000 |
| Loki | http://localhost:3100 | http://loki:3100 |
| Jaeger UI | http://localhost:16686 | http://jaeger:16686 |
| cAdvisor | http://localhost:8080 | http://cadvisor:8080 |

Grafana is provisioned with `admin` / `admin` for this local simulation only. Do not use these credentials in a deployed environment.

## Startup and validation

```powershell
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs otel-collector
```

The four original services must be running before telemetry is considered valid. The Collector, Prometheus, Grafana, Loki, Jaeger, and cAdvisor should also show `Up` in `docker compose ps`.

Generate one end-to-end request:

```powershell
$body = '{"user_id":1,"product_id":1,"quantity":1}'
Invoke-RestMethod -Method Post -Uri http://localhost:8003/orders -ContentType 'application/json' -Body $body
```

For sustained data, start the optional traffic generator:

```powershell
docker compose --profile traffic up -d traffic-generator
docker compose logs -f traffic-generator
```

The generator creates a fixture user/product when the database is empty and continuously exercises users, products, and orders. Stop it with `docker compose stop traffic-generator`.

## Metrics

The service middleware exports the following OpenTelemetry instruments through the Collector's Prometheus exporter:

| Metric | Type | Meaning |
| --- | --- | --- |
| `app_http_request_count_total` | counter | All HTTP requests |
| `app_http_error_count_total` | counter | HTTP requests returning 5xx |
| `app_http_request_duration_seconds` | histogram | Request duration |

Resource labels include `service_name` and `deployment_environment`; measurement labels include `http_method` and `http_status_code` after Prometheus translation.

Useful PromQL queries:

```promql
sum by (service_name) (rate(app_http_request_count_total[1m]))
sum by (service_name) (rate(app_http_error_count_total[1m]))
histogram_quantile(0.95, sum by (le, service_name) (rate(app_http_request_duration_seconds_bucket[5m])))
sum by (name) (rate(container_cpu_usage_seconds_total{name=~"user-service|product-service|order-service"}[5m])) * 100
sum by (name) (container_memory_working_set_bytes{name=~"user-service|product-service|order-service"})
```

Prometheus target health is available at http://localhost:9090/targets. The `otel-collector` and `cadvisor` targets should be `UP`.

## Logs and Loki queries

Existing application logging is retained. The OpenTelemetry logging handler sends log records to the Collector, which exports them to Loki. Resource labels include `service_name` and `deployment_environment`; severity is available as `level`.

Example LogQL queries in Grafana Explore:

```logql
{service_name="order-service"}
{service_name="order-service"} | level = "ERROR"
{service_name="product-service"} |= "Product created"
{service_name="order-service"} |= "User service unavailable"
{service_name="order-service"} |= "Order created successfully"
```

The Loki readiness endpoint is http://localhost:3100/ready.

## Distributed traces

FastAPI creates the server span. HTTPX creates child client spans for the Order Service's calls to User and Product Service. SQLAlchemy creates database spans. W3C Trace Context propagation preserves the same trace ID across these calls.

Expected logical trace:

```text
POST /orders (order-service)
  ├─ GET /users/{id} (user-service)
  ├─ SELECT ... (PostgreSQL, from order-service if applicable)
  └─ GET /products/{id} (product-service)
```

Open http://localhost:16686, select a service such as `order-service`, and find the `POST /orders` trace. A trace has one trace ID; each operation has its own span ID and parent span ID. The span durations show where latency is spent, and an error status identifies a failed downstream call.

## Controlled incident validation

Run the traffic generator first so the dashboards have a baseline.

### User Service failure

```powershell
docker compose stop user-service
# Generate an order request, or let traffic-generator continue running.
docker compose start user-service
```

Expected evidence: Order Service 5xx/error-count increase, an `User service unavailable` log, and a failed/slow HTTP client span in Jaeger.

### Product Service failure

```powershell
docker compose stop product-service
docker compose start product-service
```

Expected evidence: the same cross-source pattern with Product Service as the failed downstream dependency.

### Database failure

```powershell
docker compose stop postgres
docker compose start postgres
```

Expected evidence: database connection errors in service logs, failed SQL spans, and increased HTTP error metrics. The existing application uses `pool_pre_ping`, so allow a few seconds after restart for the database to become healthy.

### Latency incident

Use a temporary delay in a controlled endpoint only when demonstrating latency. Rebuild that one service, observe the request-duration histogram and long Jaeger span, then remove the delay and rebuild again. Do not leave artificial latency enabled in the normal branch.

## Person 3 data handoff

The normalized evidence layer can consume:

- Prometheus at `http://prometheus:9090`; query with `GET /api/v1/query?query=...` and range query with `GET /api/v1/query_range`.
- Loki at `http://loki:3100`; query with `GET /loki/api/v1/query_range?query={service_name="order-service"}`.
- Jaeger at `http://jaeger:16686`; the UI is human-facing, while the Jaeger query API can be used to retrieve services, traces, and spans. The trace ID is the stable correlation key.

Each telemetry record should preserve its source timestamp, `service.name`, `deployment.environment`, severity/status, trace ID, and span ID where present. A useful incident record can add an application-generated incident ID, deployment version, Git commit, and the observed time window during normalization.

Example normalized evidence fields:

```json
{
  "source": "loki",
  "timestamp": "2026-08-23T10:02:11.123Z",
  "service": "order-service",
  "level": "ERROR",
  "message": "User service unavailable",
  "trace_id": "optional-32-hex-character-id",
  "span_id": "optional-16-hex-character-id"
}
```

## Troubleshooting

- `docker compose config` fails: check that every path under `observability/` exists and that the YAML indentation is unchanged.
- Collector restarts: run `docker compose logs otel-collector`; configuration errors normally identify the receiver/exporter field.
- No metrics: wait at least 5 seconds for the SDK metric reader and then inspect `http://localhost:9464/metrics` and Prometheus `/targets`.
- No logs in Loki: generate a request, wait for the Collector batch interval, then check `docker compose logs otel-collector` and query Loki readiness.
- No trace in Jaeger: confirm the Collector and Jaeger are running, generate a new order after startup, and search the `order-service` service in Jaeger.
- Services cannot connect to one another: use container DNS names (`user-service`, `product-service`, `postgres`, and `otel-collector`), not host ports or `localhost`.
- Database data is persisted in the Compose volume. Use `docker compose down`, not `docker compose down -v`, when stopping the environment without intentionally deleting the database and telemetry data.

## Shutdown

```powershell
docker compose stop
```

Use `docker compose down` to remove containers while retaining named volumes. Do not use `docker compose down -v` unless deleting local database and observability history is intentional.
