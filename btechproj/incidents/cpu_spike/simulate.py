"""
CPU Spike Incident Simulator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Activates CPU-burning threads *inside* the order-service process via its
built-in ``/admin/fault`` API.  No ``docker exec``, no ``os.fork()``,
no PID tracking — just a single HTTP POST to start and DELETE to stop.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from incidents._common import (
    GracefulExit, IncidentState, banner, base_argparser, clamp_duration,
    clear_fault, emit_phase, find_project_root, finish_recovery,
    inject_fault, observe_baseline, require_container,
    start_traffic_generator, wait_for_duration,
)

INCIDENT_ID = "INC-004"
INCIDENT_TYPE = "cpu_spike"
DEFAULT_SERVICE = "order-service"


def recover(root: Path, state: IncidentState) -> None:
    clear_fault(state.target_service)


def main() -> int:
    parser = base_argparser(
        "Burn CPU inside an application container via the built-in fault API."
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="CPU worker threads (default 2, max 4).",
    )
    args = parser.parse_args()
    root = find_project_root()

    previous = IncidentState.load(INCIDENT_TYPE)
    if args.recover:
        if previous:
            recover(root, previous)
            emit_phase("recovered", incident_id=INCIDENT_ID)
            finish_recovery(
                root, previous, args.recovery_seconds,
                "http://localhost:8003/health",
            )
        return 0
    if previous:
        parser.error("A prior run needs recovery. Re-run with --recover.")

    service = args.service or DEFAULT_SERVICE
    duration = clamp_duration(args.duration)
    workers = max(1, min(int(args.workers * max(args.intensity, 0.1)), 4))

    if args.dry_run:
        emit_phase(
            "dry_run", incident_id=INCIDENT_ID,
            action=f"start {workers} CPU worker threads in {service}",
            duration_seconds=duration,
        )
        return 0

    cid = require_container(service, root)
    traffic_started = start_traffic_generator(root)

    state = IncidentState(
        INCIDENT_ID, INCIDENT_TYPE, service, cid,
        {"traffic_started": traffic_started},
    )
    state.save()

    try:
        with GracefulExit():
            observe_baseline(args.baseline_seconds, INCIDENT_ID)
            banner(INCIDENT_ID, INCIDENT_TYPE, service, "injecting")

            inject_fault(
                service, "cpu",
                workers=workers,
                duration_seconds=duration + 60,
            )

            emit_phase(
                "injected", incident_id=INCIDENT_ID,
                service=service, workers=workers,
            )
            wait_for_duration(duration, INCIDENT_ID)
    finally:
        recover(root, state)
        emit_phase("recovered", incident_id=INCIDENT_ID, service=service)
        finish_recovery(
            root, state, args.recovery_seconds,
            "http://localhost:8003/health",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
