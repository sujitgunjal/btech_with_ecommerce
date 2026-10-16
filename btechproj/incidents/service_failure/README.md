# Incident: service_failure

## Purpose
Simulate one application service becoming unavailable.

## Affected Service
An application compose service (auto-detected; override with `--service`).

## Severity
HIGH

## Expected Root Cause (GROUND TRUTH)
The service process is unresponsive.

## Expected Symptoms
5xx, connection refused, failed traces.

## Expected Evidence
Upstream 5xx counters, Jaeger missing spans, docker pause event.

## Timeline
T+0 baseline → T+2 pause → T+90 unpause → T+95 recovered.

## How to Run
```bash
python incidents/service_failure/simulate.py --service order-service --duration 90