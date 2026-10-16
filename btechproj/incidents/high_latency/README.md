# Incident: high_latency

## Purpose
Inject bounded latency only on the order-service to product-service path.

## Affected Service
Application compose service (auto-detected, override with `--service`).

## Severity
MEDIUM

## Expected Root Cause (GROUND TRUTH)
Bounded delay on the product-service dependency transport.

## Expected Symptoms
- successful but significantly slower order requests
- healthy unrelated service paths
- slow dependency traces

## Expected Evidence
Prometheus latency histogram shift, Jaeger spans.

## Timeline
T+0 baseline → T+2 delay applied → T+90 removed → T+95 recovered.

## How to Run
```bash
python incidents/high_latency/simulate.py --service order-service --delay-ms 1500 --duration 90