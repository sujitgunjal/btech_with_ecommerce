# Incident: memory_spike

## Purpose
Temporarily raise memory usage inside one container.

## Affected Service
Application compose service.

## Severity
HIGH

## Expected Root Cause (GROUND TRUTH)
Injected allocation inside the target container.

## Expected Symptoms
Rising `container_memory_working_set_bytes` while requests continue.

## Expected Evidence
cAdvisor memory series with an elevated plateau followed by recovery.

## Timeline
T+0 baseline → T+5 alloc → T+90 release → T+95 recovered.

## How to Run
```bash
python incidents/memory_spike/simulate.py --service order-service --megabytes 200 --duration 90