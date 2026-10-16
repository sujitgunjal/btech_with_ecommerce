# Scenario catalogue

These scenarios are the ground truth for comparing an AI investigation with what the lab actually did. The shop stores `expected_root_cause` on the experiment row and returns it from the operator API. It is not written into application logs, traces, or metrics.

Run a scenario from the lab at http://localhost:8088/ops, note the start and end time, then point the existing investigation system at service `ecommerce-shop-api` or `ecommerce-payment-gateway` for that window. Compare its report with the experiment row. Do not paste the expected root cause into a ticket the investigator can read.

| ID | Kind | What changes | Signals to expect | Root cause the AI should reach |
| --- | --- | --- | --- | --- |
| cpu_high | fault | Bounded CPU loop inside the selected process | Container CPU and slower `app_http_request_duration_seconds` | The process was CPU-saturated by an in-process burn |
| memory_pressure | fault | Retained memory allocation, 16–96 MB | `container_memory_working_set_bytes` steps up | The process retained a large memory block |
| slow_responses | fault | Delay before ordinary responses | Latency histogram shifts, low error rate | Responses were delayed inside the service |
| elevated_5xx | fault | A share of requests return HTTP 500 | `app_http_error_count_total`, 500 logs | The service failed a portion of requests with HTTP 500 |
| db_latency | fault | Sleep before each SQL statement | Long SQL spans and slower shop requests | Database statements were delayed |
| db_pool_exhaustion | fault | Holds the SQLAlchemy pool | Pool gauge at the pool size, HTTP 503, pool-exhausted logs | New requests could not get a database connection |
| payment_timeout | fault | Gateway sleeps longer than the shop's 2s timeout | Client timeout spans, payment failure counter | The gateway answered too slowly for the shop timeout |
| payment_failure | fault | Gateway returns HTTP 502 | 502 spans on the gateway, checkout errors on the shop | The gateway failed the charge |
| inventory_conflict | fault | Checkout reservations are rejected | `ecommerce_inventory_conflict_count`, HTTP 409 | Checkout could not reserve stock |
| slow_search | fault | Delay only when a search query is present | Slow `GET /products?q=` spans | Product search handling was delayed |
| slow_checkout | fault | Delay inside checkout only | `ecommerce_order_processing_duration` | Checkout processing was delayed |
| service_unavailable | fault | Customer routes return HTTP 503 | 503s on the selected service | The service was unavailable |
| dependency_timeout | fault | Shop gives the gateway 0.4s while the gateway delays | Short client timeouts and longer gateway spans | The shop stopped waiting for the payment gateway |
| browse_load | load | Real catalogue reads at a capped rate | Request-rate slope, no fault flag | Customer browse traffic increased the request rate |
| search_load | load | Real search reads | Search request rate and SQL time | Search traffic increased read load |
| checkout_load | load | Real checkouts as `loadbot@northline.shop` | Paid orders, stock decreases, genuine 409 only if stock hits zero | Concurrent checkout contended for stock |
| mixed_load | load | Browse, search, and checkout together | Mixed endpoint rates | Mixed customer traffic, with no fault flag |

Load tests and fault injection are separate code paths. The lab allows only one experiment at a time so a latency spike is not both a delay flag and a traffic surge. Fault injection is off unless `APP_ENV` is `development` or `testing` and `FAULT_INJECTION_ENABLED=true`.
