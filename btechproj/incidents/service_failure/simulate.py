from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from incidents._common import (
    GracefulExit, IncidentState, banner, base_argparser, clamp_duration,
    emit_phase, find_project_root, finish_recovery, observe_baseline,
    pause_container, require_container, start_traffic_generator,
    unpause_container, wait_for_duration,
)

INCIDENT_ID = "INC-002"
INCIDENT_TYPE = "service_failure"
DEFAULT_SERVICE = "product-service"


def recover(root: Path, state: IncidentState) -> None:
    if state.container_id:
        unpause_container(state.container_id)


def main() -> int:
    parser = base_argparser("Pause one application container to simulate an unavailable dependency.")
    args = parser.parse_args()
    root = find_project_root()
    previous = IncidentState.load(INCIDENT_TYPE)
    if args.recover:
        if previous:
            recover(root, previous)
            emit_phase("recovered", incident_id=INCIDENT_ID)
            finish_recovery(root, previous, args.recovery_seconds, "http://localhost:8002/health")
        return 0
    if previous:
        parser.error("A prior run needs recovery. Re-run with --recover.")

    service = args.service or DEFAULT_SERVICE
    duration = clamp_duration(args.duration)
    if args.dry_run:
        emit_phase("dry_run", incident_id=INCIDENT_ID, action=f"pause {service}", duration_seconds=duration)
        return 0

    cid = require_container(service, root)
    traffic_started = start_traffic_generator(root)
    state = IncidentState(INCIDENT_ID, INCIDENT_TYPE, service, cid, {"traffic_started": traffic_started})
    state.save()
    try:
        with GracefulExit():
            observe_baseline(args.baseline_seconds, INCIDENT_ID)
            banner(INCIDENT_ID, INCIDENT_TYPE, service, "injecting")
            pause_container(cid)
            emit_phase("injected", incident_id=INCIDENT_ID, service=service, container_id=cid)
            wait_for_duration(duration, INCIDENT_ID)
    finally:
        recover(root, state)
        emit_phase("recovered", incident_id=INCIDENT_ID, service=service)
        finish_recovery(root, state, args.recovery_seconds, "http://localhost:8002/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
