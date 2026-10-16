# Northline

Customer shop used as a realistic application in front of the existing AI incident investigation stack. The shop is a separate Compose project. It does not import or call the investigation backend.

Customers can register, sign in, browse and search the catalogue, filter by category and stock, save a wishlist, check out, and follow an order. A separate lab page can run bounded fault injection or a load test. Those controls are off unless you enable them.

## Architecture

```text
Browser
  │
  ├─ ecommerce-frontend :8088  nginx, proxies /api to the shop
  │
  ├─ ecommerce-shop-api :8100  FastAPI, PostgreSQL, JWT
  │     └─ HTTP charges
  └─ ecommerce-payment-gateway :8101  simulated card gateway

Both APIs export OTLP/gRPC to OTEL_EXPORTER_OTLP_ENDPOINT.
Joining a Docker network does not configure that exporter.
```

| Piece | Role |
| --- | --- |
| `frontend/` | React + Vite storefront and the lab page |
| `backend/shop_api/` | Customer API |
| `backend/payment_service/` | Simulated payment gateway |
| `backend/shop_platform/` | Telemetry, JSON logs, fault limits, catalogue loader |
| `scenarios/catalogue.json` | Fixed scenarios, bounds, and expected root causes |
| `ecommerce-postgres` | Shop database, host port 5433 |

The existing project under `btechproj/` is unchanged.

## Run the shop on its own

From `ecommerce`:

```powershell
docker compose up -d --build
```

| URL | What |
| --- | --- |
| http://localhost:8088 | Shop |
| http://localhost:8100/docs | Shop API |
| http://localhost:8101/health | Payment gateway |
| localhost:5433 | PostgreSQL (`shop` / `shop`, database `shop`) |

Sample customer: `demo@northline.shop` / `DemoPass123!`

Checkout cards:

| Number | Result |
| --- | --- |
| 4242424242424242 | Approved |
| 4000000000000002 | Declined, stock restored |
| 4000000000009995 | Gateway timeout, stock restored |

Shipping is $5, and free from $75. A repeated `Idempotency-Key` returns the original order and does not sell the same stock twice. Stock updates use a conditional decrement inside the order transaction.

For frontend development without rebuilding the image:

```powershell
cd frontend
npm install
npm run dev
```

Vite is on http://localhost:5174 and proxies `/api` to http://localhost:8100. The API container must already be running.

## Environment

Copy `.env.example` to `.env` before changing secrets. Compose substitutes these variables. The safe defaults leave the lab unavailable.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` refuses the lab even if the flag is set |
| `FAULT_INJECTION_ENABLED` | `false` | Master switch for the lab |
| `JWT_SECRET` | dev placeholder | Customer and operator tokens |
| `PAYMENT_SHARED_SECRET` | dev placeholder | Shop-to-gateway credential |
| `INTERNAL_FAULT_TOKEN` | dev placeholder | Shop-to-gateway fault control |
| `OPS_USERNAME` / `OPS_PASSWORD` | empty | Lab login. Password must be at least 5 characters |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://host.docker.internal:4317` | Collector. Empty disables export |
| `PAYMENT_TIMEOUT_SECONDS` | `2` | How long checkout waits for the gateway |
| `DB_POOL_SIZE` | `5` | SQLAlchemy pool. Overflow is 0 |
| `DB_POOL_TIMEOUT` | `2` | Seconds to wait for a connection |

`APP_ENV=production` also requires a real `JWT_SECRET`. The process refuses to start when that value is still `change-me`.

## API

Customer routes, all under the shop API:

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/auth/register`, `/auth/login` | Returns a JWT |
| GET | `/auth/me` | Current customer |
| PATCH | `/profile` | Name, phone, address |
| POST | `/profile/password` | Current password required |
| GET | `/categories` | Categories and counts |
| GET | `/products` | `q`, `category`, `min_price`, `max_price`, `in_stock`, `sort`, `limit`, `offset`. Prices are cents |
| GET | `/products/{slug}` | Product detail |
| GET/POST | `/cart`, `/cart/items` | Cart. Quantity is capped at 10 and at stock |
| PATCH/DELETE | `/cart/items/{id}` | Update or remove |
| GET/POST/DELETE | `/wishlist`, `/wishlist/{product_id}` | Saved products |
| POST | `/checkout` | Requires `Idempotency-Key` |
| GET | `/orders`, `/orders/{id}` | History and tracking |
| GET | `/health`, `/health/ready` | Liveness and database |

Operator routes return 404 unless the environment is `development` or `testing`, `FAULT_INJECTION_ENABLED=true`, and both operator credentials are set.

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/ops/login` | Operator JWT, separate from customer tokens |
| GET | `/ops/scenarios` | Catalogue, including bounds |
| GET | `/ops/status` | Active fault or load test |
| GET | `/ops/experiments` | History, including expected root cause |
| POST | `/ops/faults` | Start a fault. Body is scenario, service, and bounded integers |
| POST | `/ops/faults/stop` | Stop the running fault |
| POST | `/ops/load` | Start load. Does not set a fault flag |
| POST | `/ops/load/stop` | Stop the load generator |

The lab rejects unknown parameters and anything named like a command, query, image, or shell. CPU is capped at 2 workers, memory at 96 MB, and duration at 120 seconds. Load rate is capped at 15 requests per second and concurrency at 8. Only one experiment runs at a time. Each one expires on its own if you do not stop it.

## Enable the lab

In `.env`:

```text
FAULT_INJECTION_ENABLED=true
OPS_USERNAME=operator
OPS_PASSWORD=choose-a-long-password
APP_ENV=development
```

Then `docker compose up -d --build` and open http://localhost:8088/ops.

The load-test customer is `loadbot@northline.shop`. Checkout load buys the Studio Tote and will reduce its stock. That is a real inventory change, not a fault flag.

In development, a paid order moves to shipped and then delivered on a short timer so tracking has something to show. That clock is off when `APP_ENV` is `testing` or `production`.

## Telemetry and the existing DevOps stack

Start the existing stack first so the collector is listening:

```powershell
cd ..\btechproj
docker compose up -d
```

The collector already publishes OTLP/gRPC on host port 4317, OTLP/HTTP on 4318, and its Prometheus exporter on 9464. Prometheus in that project scrapes `otel-collector:9464`. Loki and Jaeger receive logs and traces from the collector pipelines in `btechproj/observability/otel/otel-collector-config.yaml`.

Northline does not join `devops-network`. Each API process sends OTLP/gRPC to `http://host.docker.internal:4317`. That hostname is mapped with `extra_hosts` in this Compose file. If you clear `OTEL_EXPORTER_OTLP_ENDPOINT`, the shop still serves traffic and simply does not export.

You do not add a Prometheus scrape job for the shop. Metrics arrive through the collector's Prometheus exporter, which is already scraped. Resource attribute `service.name` becomes the `service_name` label because that collector config enables `resource_to_telemetry_conversion`.

Instruments match the existing queries:

| Metric | Meaning |
| --- | --- |
| `app_http_request_count_total` | Requests, with `service_name` |
| `app_http_error_count_total` | HTTP 5xx |
| `app_http_request_duration_seconds` | Latency histogram |
| `ecommerce_payment_failure_count_total` | Charge timeouts and failures |
| `ecommerce_checkout_error_count_total` | Checkouts that did not end as paid |
| `ecommerce_inventory_conflict_count_total` | Rejected reservations |
| `ecommerce_order_processing_duration_seconds` | Checkout duration |

Stdout logs are JSON and include `trace_id` and `span_id` when a span is current. The same records are exported as OTLP logs, and the existing collector forwards those to Loki. Traces use W3C propagation through the HTTP call from the shop to the payment gateway. FastAPI, HTTPX, and SQLAlchemy are instrumented.

Useful names when you open an investigation:

| Signal | Name to use |
| --- | --- |
| HTTP metrics and traces | `ecommerce-shop-api` or `ecommerce-payment-gateway` |
| Container CPU and memory | Compose service `ecommerce-shop-api` or `ecommerce-payment-gateway` |

cAdvisor in the existing project sees every container on the Docker engine, so those CPU and memory series appear without a new scrape job. Create the incident in the existing UI for the experiment's time window. Compare the report with `GET /ops/experiments`. The expected root cause is only on that row. It is intentionally absent from logs, so the investigator has to use the telemetry.

If the collector is not running, the shop logs exporter errors and continues to answer requests.

## Tests

From `ecommerce/backend`, with the virtualenv created:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q
```

The suite covers registration and login, catalogue search, cart and checkout, duplicate idempotency keys, declined and timed-out payments, concurrent stock reservation, metric names, catalogue bounds, the lab's default-off switch, fault start/stop, and the separation between load tests and fault flags. Tests use SQLite and do not need Docker.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Shop API restarts | `docker compose logs ecommerce-shop-api`. Postgres must be healthy first |
| Lab returns 404 | `FAULT_INJECTION_ENABLED`, `APP_ENV`, and both operator credentials |
| Checkout cannot reach the gateway | `docker compose ps` and `PAYMENT_SHARED_SECRET` must match on both services |
| No series in Prometheus | Collector is up, and `OTEL_EXPORTER_OTLP_ENDPOINT` is `http://host.docker.internal:4317` |
| Jaeger has no shop traces | Same endpoint. Search service `ecommerce-shop-api` |
| Load test sells out the tote | Studio Tote stock is real. Recreate the database volume to reseed |
| Port already in use | This project uses 5433, 8088, 8100, and 8101 so it can sit beside `btechproj` |

Stop the shop with `docker compose stop`. `docker compose down` removes containers and keeps the database volume. `docker compose down -v` deletes the shop database.
