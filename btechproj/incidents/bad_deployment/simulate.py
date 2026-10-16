from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from incidents._common import (
    GracefulExit, IncidentState, banner, base_argparser, clamp_duration,
    container_environment, emit_phase, find_project_root, finish_recovery,
    observe_baseline, recreate_order_service, require_container,
    start_traffic_generator, wait_for_duration, wait_for_http,
)

INCIDENT_ID = "INC-006"
INCIDENT_TYPE = "bad_deployment"
DEFAULT_SERVICE = "order-service"


def recover(root: Path, state: IncidentState) -> None:
    recreate_order_service(
        root,
        state.extras.get("previous_version", "v1.3.1"),
        state.extras.get("previous_fault_mode", "none"),
    )
    wait_for_http("http://localhost:8003/health")


def main() -> int:
    parser = base_argparser(
        "Deploy a reproducible order-service regression and roll back to the prior version."
    )
    args = parser.parse_args()
    root = find_project_root()
    previous = IncidentState.load(INCIDENT_TYPE)
    if args.recover:
        if previous:
            recover(root, previous)
            emit_phase("recovered", incident_id=INCIDENT_ID)
            finish_recovery(root, previous, args.recovery_seconds, "http://localhost:8003/health")
        return 0
    if previous:
        parser.error("A prior run needs recovery. Re-run with --recover.")

    service = args.service or DEFAULT_SERVICE
    duration = clamp_duration(args.duration)
    if args.dry_run:
        emit_phase(
            "dry_run", incident_id=INCIDENT_ID,
            action=f"deploy v1.3.0 of {service}, then roll back",
            duration_seconds=duration,
        )
        return 0

    cid = require_container(service, root)
    previous_environment = container_environment(cid)
    previous_version = previous_environment.get("ORDER_SERVICE_VERSION", "v1.3.1")
    previous_fault_mode = previous_environment.get("INCIDENT_ORDER_FAULT_MODE", "none")
    traffic_started = start_traffic_generator(root)
    state = IncidentState(
        INCIDENT_ID,
        INCIDENT_TYPE,
        service,
        cid,
        {
            "traffic_started": traffic_started,
            "previous_version": previous_version,
            "previous_fault_mode": previous_fault_mode,
        },
    )
    state.save()
    try:
        with GracefulExit():
            observe_baseline(args.baseline_seconds, INCIDENT_ID)
            banner(INCIDENT_ID, INCIDENT_TYPE, service, "injecting")
            recreate_order_service(root, "v1.3.0", "product_contract_regression")
            wait_for_http("http://localhost:8003/health")
            emit_phase(
                "injected", incident_id=INCIDENT_ID, service=service,
                deployment_version="v1.3.0",
            )
            wait_for_duration(duration, INCIDENT_ID)
    finally:
        recover(root, state)
        emit_phase(
            "recovered", incident_id=INCIDENT_ID, service=service,
            deployment_version=previous_version,
        )
        finish_recovery(root, state, args.recovery_seconds, "http://localhost:8003/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
