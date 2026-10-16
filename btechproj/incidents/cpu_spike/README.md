# Incident: cpu_spike

## Purpose
Drive CPU usage up **inside a service container** (not on the host).

## Affected Service
Application compose service.

## Severity
MEDIUM

## Expected Root Cause (GROUND TRUTH)
Injected CPU-burning workload inside the container.

## Expected Symptoms
High container CPU, rising latency, throttling.

## Expected Evidence
`container_cpu_usage_seconds_total`, latency histogram.

## Timeline
T+0 baseline → T+2 burn → T+90 stop → T+95 recovered.

## How to Run
```bash
python incidents/cpu_spike/simulate.py --service order-service --workers 2 --duration 90