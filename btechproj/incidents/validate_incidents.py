"""Validate incident ground truth and deployment history without dependencies."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCIDENTS = ROOT / "incidents"
DEPLOYMENTS = ROOT / "deployments" / "deployment_history.json"
TYPES = ("database_failure", "service_failure", "high_latency", "cpu_spike", "memory_spike", "bad_deployment", "network_failure")
REQUIRED = {"incident_id", "type", "affected_service", "start_time", "end_time", "expected_root_cause", "expected_symptoms", "severity"}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp ending in Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def git_commit_exists(commit_id: str) -> bool:
    result = subprocess.run(["git", "rev-parse", "--verify", f"{commit_id}^{{commit}}"], cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0


def main() -> int:
    errors: list[str] = []
    incident_ids: set[str] = set()
    scenarios: dict[str, dict[str, object]] = {}
    for incident_type in TYPES:
        path = INCIDENTS / incident_type / "scenario.json"
        try:
            scenario = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: unreadable JSON ({exc})")
            continue
        scenarios[incident_type] = scenario
        missing = REQUIRED - scenario.keys()
        if missing:
            errors.append(f"{path}: missing {', '.join(sorted(missing))}")
            continue
        if scenario["type"] != incident_type:
            errors.append(f"{path}: type must equal {incident_type!r}")
        incident_id = scenario["incident_id"]
        if not isinstance(incident_id, str) or not re.fullmatch(r"INC-[0-9]{3}", incident_id):
            errors.append(f"{path}: incident_id must match INC-000")
        elif incident_id in incident_ids:
            errors.append(f"{path}: duplicate incident_id {incident_id}")
        else:
            incident_ids.add(incident_id)
        if scenario["severity"] not in SEVERITIES:
            errors.append(f"{path}: unsupported severity {scenario['severity']!r}")
        if not isinstance(scenario["expected_symptoms"], list) or not scenario["expected_symptoms"]:
            errors.append(f"{path}: expected_symptoms must be a non-empty array")
        try:
            if parse_timestamp(scenario["end_time"], f"{path} end_time") <= parse_timestamp(scenario["start_time"], f"{path} start_time"):
                errors.append(f"{path}: end_time must be after start_time")
        except ValueError as exc:
            errors.append(str(exc))
    try:
        deployments = json.loads(DEPLOYMENTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{DEPLOYMENTS}: unreadable JSON ({exc})")
        deployments = []
    required_deployment = {"service", "version", "commit_id", "deployment_time", "status"}
    for index, deployment in enumerate(deployments):
        label = f"deployment_history[{index}]"
        if not isinstance(deployment, dict) or required_deployment - deployment.keys():
            errors.append(f"{label}: missing required deployment fields")
            continue
        commit_id = deployment["commit_id"]
        if not isinstance(commit_id, str) or not re.fullmatch(r"[0-9a-f]{7,40}", commit_id):
            errors.append(f"{label}: commit_id must be a Git SHA")
        elif not git_commit_exists(commit_id):
            errors.append(f"{label}: commit_id {commit_id} does not resolve")
        try:
            parse_timestamp(deployment["deployment_time"], f"{label} deployment_time")
        except ValueError as exc:
            errors.append(str(exc))
    related = scenarios.get("bad_deployment", {}).get("related_deployment")
    if isinstance(related, dict) and not any(item.get("service") == related.get("service") and item.get("version") == related.get("version") and item.get("commit_id") == related.get("commit_id") for item in deployments):
        errors.append("bad_deployment related_deployment does not match deployment_history.json")
    if errors:
        print("Incident validation failed:", file=sys.stderr)
        print(*[f"- {error}" for error in errors], sep="\n", file=sys.stderr)
        return 1
    print(f"Validated {len(scenarios)} incident scenarios and {len(deployments)} deployment events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
