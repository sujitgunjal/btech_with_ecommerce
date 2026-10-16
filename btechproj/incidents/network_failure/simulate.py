from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from incidents._common import (
    GracefulExit, IncidentState, banner, base_argparser, clamp_duration,
    configure_dependency_proxy, emit_phase, find_project_root,
    finish_recovery, observe_baseline, require_container,
    start_traffic_generator, wait_for_duration,
)

INCIDENT_ID = "INC-007"
INCIDENT_TYPE = "network_failure"
DEFAULT_SERVICE = "order-service"


def recover(root: Path, state: IncidentState) -> None:
    configure_dependency_proxy("none")


def main() -> int:
    parser = base_argparser("Drop traffic on one dependency path while telemetry remains reachable.")
    parser.add_argument("--loss-percent", type=int, choices=[100], default=100, help="Packet loss percentage (100).")
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
    loss_percent = args.loss_percent
    if args.dry_run:
        emit_phase("dry_run", incident_id=INCIDENT_ID, action=f"drop {loss_percent}% of traffic for {service}", duration_seconds=duration)
        return 0

    cid = require_container(service, root)
    traffic_started = start_traffic_generator(root)
    state = IncidentState(
        INCIDENT_ID, INCIDENT_TYPE, service, cid,
        {"traffic_started": traffic_started, "dependency_service": "product-service"},
    )
    state.save()
    try:
        with GracefulExit():
            observe_baseline(args.baseline_seconds, INCIDENT_ID)
            banner(INCIDENT_ID, INCIDENT_TYPE, service, "injecting")
            configure_dependency_proxy("drop")
            emit_phase(
                "injected", incident_id=INCIDENT_ID, service=service,
                dependency_service="product-service",
                loss_percent=loss_percent,
            )
            wait_for_duration(duration, INCIDENT_ID)
    finally:
        recover(root, state)
        emit_phase("recovered", incident_id=INCIDENT_ID, service=service)
        finish_recovery(root, state, args.recovery_seconds, "http://localhost:8003/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
