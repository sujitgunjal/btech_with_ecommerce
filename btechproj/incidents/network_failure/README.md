# Incident: network_failure

## Purpose
Simulate a network/dependency failure affecting one service.

## Affected Service
Application compose service.

## Severity
HIGH

## Expected Root Cause (GROUND TRUTH)
Packets from order-service to product-service are dropped while unrelated paths remain healthy.

## Expected Symptoms
Product dependency timeouts, order-service 503 responses, and healthy direct product requests.

## Expected Evidence
Failed product client spans, order-service 5xx counters, timeout log lines, and healthy product-service telemetry.

## Timeline
T+0 baseline → T+2 block → T+90 restore → T+95 recovered.

## How to Run
```bash
python incidents/network_failure/simulate.py --service order-service --duration 90