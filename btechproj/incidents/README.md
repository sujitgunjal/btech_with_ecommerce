# Incident Scenario Library

This directory contains deterministic incident ground truth for evaluation and replay. Each `scenario.json` states what happened, when it happened, what was affected, and the expected evidence.

The `expected_root_cause` fields are ground truth and must not be supplied to an investigator under evaluation. The matching `simulate.py` command in each scenario directory provides a reversible way to create the operational signal.

Validate the library and its deployment references with:

```powershell
python .\incidents\validate_incidents.py
```
