#!/usr/bin/env python3
"""End-to-end test for the investigation pipeline.

Tests the full flow:
1. Create incident via API
2. Trigger investigation (evidence collection + RAG + LLM)
3. Validate the structured RCA response
4. Compare RCA against ground truth (post-investigation evaluation only)

Usage:
    python -m scripts.test_investigation                  # test all 7 incidents
    python -m scripts.test_investigation --incident INC-001  # test one incident
    python -m scripts.test_investigation --dry-run           # test without LLM call

Requires the full Docker stack to be running (backend, postgres, prometheus,
loki, jaeger, microservices).
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BACKEND_URL = "http://localhost:8010"
TIMEOUT = 120.0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INCIDENTS_DIR = PROJECT_ROOT / "incidents"

SCENARIO_DIRS = {
    "INC-001": "database_failure",
    "INC-002": "service_failure",
    "INC-003": "high_latency",
    "INC-004": "cpu_spike",
    "INC-005": "memory_spike",
    "INC-006": "bad_deployment",
    "INC-007": "network_failure",
}

RCA_REQUIRED_FIELDS = [
    "root_cause",
    "supporting_evidence",
    "affected_services",
    "confidence",
    "timeline",
    "alternative_explanations",
    "recommended_actions",
    "relevant_historical_incidents",
]


def load_scenario(incident_id: str) -> dict:
    """Load scenario.json for an incident."""
    dir_name = SCENARIO_DIRS.get(incident_id)
    if not dir_name:
        raise ValueError(f"Unknown incident: {incident_id}")
    path = INCIDENTS_DIR / dir_name / "scenario.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


FAULT_HOLD_SECONDS = 70
ORDER_URL = "http://localhost:8003/orders"


def _load_simulators():
    """Import the existing incident simulators from the project root."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from incidents._common import (
        clear_fault,
        inject_fault,
        recreate_order_service,
        wait_for_http,
    )

    return inject_fault, clear_fault, recreate_order_service, wait_for_http


def _post_order() -> None:
    try:
        httpx.post(
            ORDER_URL,
            json={"user_id": 1, "product_id": 1, "quantity": 1},
            timeout=5.0,
        )
    except httpx.HTTPError:
        return


def generate_traffic(seconds: int) -> None:
    """Send order requests so logs, metrics, and traces exist during the fault."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        _post_order()
        time.sleep(1)


def activate_fault(incident_id: str, scenario: dict):
    """Inject the scenario fault and return a cleanup function.

    INC-004 and INC-005 use the order-service fault API. INC-006 deploys the
    known bad order-service version. Other incidents are not injected here.
    """
    if incident_id not in {"INC-004", "INC-005", "INC-006"}:
        return None

    inject_fault, clear_fault, recreate_order_service, wait_for_http = _load_simulators()
    service = scenario["affected_service"]

    if incident_id == "INC-004":
        inject_fault(service, "cpu", workers=2, duration_seconds=FAULT_HOLD_SECONDS + 60)
        return lambda: clear_fault(service)
    if incident_id == "INC-005":
        inject_fault(
            service, "memory", megabytes=256, duration_seconds=FAULT_HOLD_SECONDS + 60
        )
        return lambda: clear_fault(service)

    recreate_order_service(PROJECT_ROOT, "v1.3.0", "product_contract_regression")
    wait_for_http("http://localhost:8003/health")

    def restore_deployment() -> None:
        recreate_order_service(PROJECT_ROOT, "v1.3.1", "none")
        wait_for_http("http://localhost:8003/health")

    return restore_deployment


def create_incident(
    client: httpx.Client,
    scenario: dict,
    start_time: datetime,
    end_time: datetime,
) -> dict:
    """Create an incident for the exact window in which the fault was active."""
    payload = {
        "title": f"{scenario['type'].replace('_', ' ').title()} on {scenario['affected_service']}",
        "description": f"Simulated {scenario['type']} incident for testing.",
        "service": scenario["affected_service"],
        "severity": scenario.get("severity", "HIGH").lower(),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }
    resp = client.post(f"{BACKEND_URL}/incidents", json=payload)
    resp.raise_for_status()
    return resp.json()


def trigger_investigation(client: httpx.Client, incident_id: int) -> dict:
    """Trigger an investigation and wait for the result."""
    resp = client.post(
        f"{BACKEND_URL}/incidents/{incident_id}/investigate",
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def validate_rca(report: dict) -> list[str]:
    """Validate that the RCA report contains all required fields."""
    issues = []

    if report is None:
        return ["Report is None — investigation produced no RCA"]

    for field in RCA_REQUIRED_FIELDS:
        if field not in report:
            issues.append(f"Missing required field: {field}")

    if "confidence" in report:
        conf = report["confidence"]
        if not isinstance(conf, (int, float)):
            issues.append(f"confidence is not numeric: {type(conf)}")
        elif not (0.0 <= conf <= 1.0):
            issues.append(f"confidence out of range: {conf}")

    if "root_cause" in report:
        if not report["root_cause"] or not report["root_cause"].strip():
            issues.append("root_cause is empty")

    for list_field in [
        "supporting_evidence",
        "affected_services",
        "recommended_actions",
    ]:
        if list_field in report and not isinstance(report[list_field], list):
            issues.append(f"{list_field} is not a list")

    return issues


def evaluate_against_ground_truth(
    report: dict, scenario: dict, incident_id: str
) -> dict:
    """Compare the RCA against ground truth (post-investigation evaluation).

    This NEVER feeds ground truth into the investigation.
    """
    result = {
        "incident_id": incident_id,
        "incident_type": scenario.get("type", "unknown"),
        "expected_service": scenario.get("affected_service", "unknown"),
        "expected_root_cause": scenario.get("expected_root_cause", ""),
    }

    if report is None:
        result["rca_produced"] = False
        result["evaluation"] = "No RCA produced"
        return result

    result["rca_produced"] = True
    result["rca_root_cause"] = report.get("root_cause", "")
    result["rca_confidence"] = report.get("confidence", 0.0)
    result["rca_affected_services"] = report.get("affected_services", [])

    expected_service = scenario.get("affected_service", "").lower()
    rca_services = [s.lower() for s in report.get("affected_services", [])]
    result["service_match"] = expected_service in " ".join(rca_services)

    expected_type = scenario.get("type", "").lower().replace("_", " ")
    rca_text = (report.get("root_cause", "") + " ".join(
        report.get("supporting_evidence", [])
    )).lower()

    type_keywords = {
        "database_failure": ["database", "postgres", "connection", "unavailable"],
        "service_failure": ["service", "unresponsive", "paused", "container"],
        "high_latency": ["latency", "slow", "delay", "response time"],
        "cpu_spike": ["cpu", "processor", "utilization", "throttl"],
        "memory_spike": ["memory", "oom", "working set", "allocation"],
        "bad_deployment": ["deploy", "version", "rollback", "keyerror", "available_stock"],
        "network_failure": ["network", "timeout", "packet", "connectivity"],
    }
    keywords = type_keywords.get(scenario.get("type", ""), [])
    matched_keywords = [kw for kw in keywords if kw in rca_text]
    result["keyword_matches"] = matched_keywords
    result["keyword_match_ratio"] = (
        len(matched_keywords) / len(keywords) if keywords else 0.0
    )

    hist_refs = report.get("relevant_historical_incidents", [])
    result["historical_incidents_referenced"] = len(hist_refs)
    result["historical_ids"] = [h.get("incident_id", "") for h in hist_refs]

    return result


def run_test(incident_id: str, dry_run: bool = False) -> dict:
    """Run the full investigation test for one incident."""
    print(f"\n{'=' * 70}")
    print(f"  Testing Investigation: {incident_id}")
    print(f"{'=' * 70}")

    scenario = load_scenario(incident_id)
    print(f"  Type:    {scenario['type']}")
    print(f"  Service: {scenario['affected_service']}")
    print(f"  Severity: {scenario.get('severity', 'N/A')}")

    with httpx.Client(timeout=TIMEOUT) as client:
        # Check backend health
        try:
            health = client.get(f"{BACKEND_URL}/health")
            if health.status_code != 200:
                print(f"  WARNING: Backend health check returned {health.status_code}")
        except httpx.ConnectError:
            print(f"  ERROR: Cannot connect to backend at {BACKEND_URL}")
            return {"incident_id": incident_id, "error": "Backend unreachable"}

        cleanup = None
        try:
            print("\n  Injecting fault and generating telemetry...")
            window_start = datetime.now(timezone.utc)
            cleanup = activate_fault(incident_id, scenario)
            if cleanup is None:
                window_start = window_start - timedelta(minutes=15)
                print("  No fault injector for this incident; using the last 15 minutes.")
            else:
                generate_traffic(FAULT_HOLD_SECONDS)
            window_end = datetime.now(timezone.utc)
            print(
                f"  Telemetry window: {window_start.isoformat()} -> {window_end.isoformat()}"
            )

            print("\n  Creating incident...")
            try:
                incident = create_incident(client, scenario, window_start, window_end)
                db_id = incident["id"]
                ext_id = incident["external_id"]
                print(f"  Created: id={db_id} external_id={ext_id}")
            except httpx.HTTPStatusError as e:
                print(f"  ERROR creating incident: {e.response.status_code} {e.response.text}")
                return {"incident_id": incident_id, "error": f"Create failed: {e}"}

            if dry_run:
                print("  DRY RUN — skipping investigation trigger")
                return {"incident_id": incident_id, "status": "dry_run", "db_id": db_id}

            print("\n  Triggering investigation (this may take a minute)...")
            start = time.time()
            try:
                result = trigger_investigation(client, db_id)
                elapsed = time.time() - start
                print(f"  Investigation completed in {elapsed:.1f}s")
            except httpx.HTTPStatusError as e:
                print(f"  ERROR: {e.response.status_code} {e.response.text}")
                return {"incident_id": incident_id, "error": f"Investigation failed: {e}"}
            except httpx.ReadTimeout:
                print(f"  ERROR: Investigation timed out after {TIMEOUT}s")
                return {"incident_id": incident_id, "error": "Timeout"}
        finally:
            if cleanup is not None:
                print("  Clearing injected fault...")
                try:
                    cleanup()
                except Exception as exc:
                    print(f"  WARNING: fault cleanup failed: {exc}")

        print(f"\n  Status:     {result.get('status', 'N/A')}")
        print(f"  Confidence: {result.get('confidence', 'N/A')}")
        print(f"  Evidence:   {result.get('evidence_count', 0)} items")

        report = result.get("report")
        if report:
            print(f"\n  Root Cause: {report.get('root_cause', 'N/A')[:120]}")
            print(f"  Affected:   {report.get('affected_services', [])}")
            actions = report.get("recommended_actions", [])
            if actions:
                print(f"  Actions:    {actions[0][:100]}")
            hist = report.get("relevant_historical_incidents", [])
            if hist:
                print(f"  History:    {[h.get('incident_id') for h in hist]}")
        else:
            print("\n  No RCA report produced.")

        issues = validate_rca(report)
        if issues:
            print("\n  Validation issues:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("\n  Validation: PASSED")

        evaluation = evaluate_against_ground_truth(report, scenario, incident_id)
        print("\n  Ground Truth Evaluation:")
        print(f"    Service match:    {evaluation.get('service_match', False)}")
        print(f"    Keyword matches:  {evaluation.get('keyword_matches', [])}")
        print(f"    Match ratio:      {evaluation.get('keyword_match_ratio', 0.0):.0%}")
        print(f"    Historical refs:  {evaluation.get('historical_incidents_referenced', 0)}")

        return {
            "incident_id": incident_id,
            "db_id": db_id,
            "status": result.get("status"),
            "confidence": result.get("confidence"),
            "evidence_count": result.get("evidence_count", 0),
            "rca_valid": len(issues) == 0,
            "validation_issues": issues,
            "evaluation": evaluation,
            "elapsed_seconds": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(description="Test investigation pipeline")
    parser.add_argument(
        "--incident", type=str, default=None,
        help="Test a specific incident (e.g. INC-001). Default: test all."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Create incidents but do not trigger investigations."
    )
    args = parser.parse_args()

    incident_ids = (
        [args.incident.upper()] if args.incident else list(SCENARIO_DIRS.keys())
    )

    print(f"\n{'#' * 70}")
    print(f"  Investigation Pipeline Test")
    print(f"  Incidents: {', '.join(incident_ids)}")
    print(f"  Backend:   {BACKEND_URL}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"{'#' * 70}")

    results = []
    for inc_id in incident_ids:
        try:
            result = run_test(inc_id, dry_run=args.dry_run)
            results.append(result)
        except Exception as e:
            print(f"\n  EXCEPTION for {inc_id}: {e}")
            results.append({"incident_id": inc_id, "error": str(e)})

    # Summary
    print(f"\n\n{'#' * 70}")
    print(f"  SUMMARY")
    print(f"{'#' * 70}")

    total = len(results)
    passed = sum(1 for r in results if r.get("rca_valid", False))
    failed = sum(1 for r in results if "error" in r)
    partial = total - passed - failed

    print(f"\n  Total:   {total}")
    print(f"  Passed:  {passed}")
    print(f"  Partial: {partial}")
    print(f"  Failed:  {failed}")

    for r in results:
        inc = r.get("incident_id", "?")
        status = r.get("status", r.get("error", "unknown"))
        conf = r.get("confidence", "-")
        valid = "PASS" if r.get("rca_valid") else "FAIL"
        ev = r.get("evaluation", {})
        kw_ratio = ev.get("keyword_match_ratio", 0.0)
        print(
            f"  {inc}: status={status} confidence={conf} "
            f"validation={valid} keyword_match={kw_ratio:.0%}"
        )

    # Save results to file
    output_path = PROJECT_ROOT / "backend" / "data" / "test_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
