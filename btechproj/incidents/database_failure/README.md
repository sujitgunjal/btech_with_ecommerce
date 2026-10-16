# Incident: database_failure

## Purpose
Simulate PostgreSQL becoming unreachable so the observability stack can capture
the resulting application symptoms for the future RAG/LLM investigator.

## Affected Service
The PostgreSQL compose service (auto-detected from `docker-compose.yml`) and,
transitively, every application service that talks to it.

## Severity
CRITICAL

## Expected Root Cause (GROUND TRUTH — never given to the LLM)
The PostgreSQL database became unavailable.

## Expected Symptoms
- HTTP 5xx from dependent services
- Elevated error rate
- Increased latency (connection timeouts)
- Failed traces with DB spans

## Expected Evidence
- `connection refused` / `OperationalError` log lines
- Prometheus 5xx counter spike
- Jaeger failed traces

## Timeline
T+0 baseline → T+2 pause → T+5 first 5xx → T+90 unpause → T+95 recovery.

## How to Run
```bash
python incidents/database_failure/simulate.py --duration 90