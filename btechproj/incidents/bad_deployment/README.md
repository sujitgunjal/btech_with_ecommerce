# Incident: bad_deployment

## Purpose
Simulate a deployment that introduces a defect.

## Affected Service
Application compose service.

## Severity
HIGH

## Expected Root Cause (GROUND TRUTH)
The deployed version expects a product response field that the dependency does not provide.

## Expected Symptoms
Order creation changes from HTTP 201 to HTTP 500 at deployment time and recovers after rollback.

## Expected Evidence
- `deployments/deployment_history.json` entry with matching timestamp
- Successful product dependency spans beneath failed order-service spans
- Order-service response-processing exception logs
- Prometheus error counter step

## Timeline
T+0 baseline → T+2 bad deploy → T+10 errors → T+120 rollback → T+130 recovered.

## How to Run
```bash
python incidents/bad_deployment/simulate.py --service order-service --duration 120