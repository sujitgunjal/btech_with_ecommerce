"""
Memory Spike Incident Simulator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Allocates a resident memory block *inside* the order-service process via its
built-in ``/admin/fault`` API.  No ``docker exec``, no PID tracking — just a
single HTTP POST to start and DELETE to stop.
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

INCIDENT_ID = "INC-005"
INCIDENT_TYPE = "memory_spike"
DEFAULT_SERVICE = "order-service"


def recover(root: Path, state: IncidentState) -> None:
    clear_fault(state.target_service)


def main() -> int:
    parser = base_argparser(
        "Allocate bounded memory inside an application container via the built-in fault API."
    )
    parser.add_argument(
        "--megabytes", type=int, default=200,
        help="Memory allocation in MiB (default 200, max 512).",
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
    megabytes = max(16, min(int(args.megabytes * max(args.intensity, 0.1)), 512))

    if args.dry_run:
        emit_phase(
            "dry_run", incident_id=INCIDENT_ID,
            action=f"allocate {megabytes} MiB in {service}",
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
                service, "memory",
                megabytes=megabytes,
                duration_seconds=duration + 60,
            )

            emit_phase(
                "injected", incident_id=INCIDENT_ID,
                service=service, megabytes=megabytes,
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
