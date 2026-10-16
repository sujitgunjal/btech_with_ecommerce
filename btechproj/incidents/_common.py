"""
Shared utilities for incident simulations.

Design goals:
- Zero required third-party dependencies (pyyaml optional; stdlib fallback).
- Never hard-code service/container names: discover from docker-compose.yml.
- Never run destructive Docker commands.
- Always leave a recoverable state trail.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("incident")


# --------------------------------------------------------------------------- #
# Project root discovery
# --------------------------------------------------------------------------- #
def find_project_root(start: Path | None = None) -> Path:
    """Walk upward until a docker-compose.yml is found."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "docker-compose.yml").is_file():
            return parent
    raise FileNotFoundError(
        "docker-compose.yml not found. Run this from inside the project tree."
    )


# --------------------------------------------------------------------------- #
# Minimal docker-compose parser (stdlib fallback)
# --------------------------------------------------------------------------- #
def _parse_compose_minimal(text: str) -> dict[str, Any]:
    """
    Very small YAML subset parser sufficient for extracting `services:` keys
    and simple scalar fields. Prefer pyyaml if available.
    """
    services: dict[str, dict[str, Any]] = {}
    in_services = False
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^services\s*:\s*$", line):
            in_services = True
            continue
        if in_services and re.match(r"^[A-Za-z]", line):  # top-level key again
            in_services = False
        if not in_services:
            continue
        m = re.match(r"^  ([A-Za-z0-9_.-]+)\s*:\s*$", line)
        if m:
            current = m.group(1)
            services[current] = {}
            continue
        m = re.match(r"^    ([A-Za-z0-9_.-]+)\s*:\s*(.+?)\s*$", line)
        if m and current:
            services[current][m.group(1)] = m.group(2).strip("'\"")
    return {"services": services}


def load_compose(root: Path | None = None) -> dict[str, Any]:
    root = root or find_project_root()
    compose_path = root / "docker-compose.yml"
    text = compose_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except Exception:
        return _parse_compose_minimal(text)


def compose_service_names(root: Path | None = None) -> list[str]:
    return sorted(load_compose(root).get("services", {}).keys())


def discover_service(
    role: str,
    root: Path | None = None,
    explicit: str | None = None,
) -> str:
    """
    Resolve a logical role ("postgres", "app") to a real compose service name.

    If `explicit` is provided (env var / CLI), it wins.
    Otherwise, heuristics are applied over the actual compose services.
    Raises a clear error listing what WAS found if nothing matches.
    """
    if explicit:
        return explicit
    services = compose_service_names(root)
    if not services:
        raise RuntimeError("No services found in docker-compose.yml.")

    patterns = {
        "postgres": [r"postgres", r"db", r"database"],
        "app": [r"order", r"api", r"backend", r"app", r"service"],
    }
    for pat in patterns.get(role, []):
        for name in services:
            if re.search(pat, name, re.IGNORECASE):
                return name
    raise RuntimeError(
        f"Could not auto-detect a service for role={role!r}. "
        f"Available services: {services}. "
        f"Pass --service or set INCIDENT_{role.upper()}_SERVICE."
    )


# --------------------------------------------------------------------------- #
# Docker CLI wrappers (safe subset)
# --------------------------------------------------------------------------- #
def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    log.debug("$ %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        cwd=cwd,
        env=env,
    )


def docker_available() -> bool:
    try:
        run(["docker", "version", "--format", "{{.Server.Version}}"])
        return True
    except Exception:
        return False


def container_id(service: str, root: Path | None = None) -> str | None:
    """Resolve compose service -> running container id."""
    root = root or find_project_root()
    try:
        cp = run(
            ["docker", "compose", "-f", str(root / "docker-compose.yml"), "ps", "-q", service],
            check=False,
            cwd=root,
        )
        cid = cp.stdout.strip().splitlines()
        return cid[0] if cid else None
    except Exception:
        return None


def pause_container(cid: str) -> None:
    run(["docker", "pause", cid])


def unpause_container(cid: str) -> None:
    cp = run(["docker", "unpause", cid], check=False)
    if cp.returncode:
        log.warning("Could not unpause container %s: %s", cid, cp.stderr.strip())


def exec_in_container(cid: str, argv: list[str], detach: bool = False) -> subprocess.CompletedProcess:
    base = ["docker", "exec"]
    if detach:
        base.append("-d")
    base.append(cid)
    base.extend(argv)
    return run(base, check=False)


def require_container(service: str, root: Path) -> str:
    cid = container_id(service, root)
    if not cid:
        raise RuntimeError(
            f"No running container found for compose service {service!r}. "
            "Start the environment with 'docker compose up -d' first."
        )
    return cid


def compose(
    root: Path,
    *args: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    return run(
        ["docker", "compose", "-f", str(root / "docker-compose.yml"), *args],
        check=False,
        cwd=root,
        env=env,
    )


def start_traffic_generator(root: Path) -> bool:
    """Start the optional Compose traffic generator only when it was not running."""
    if container_id("traffic-generator", root):
        return False
    cp = compose(root, "--profile", "traffic", "up", "-d", "traffic-generator")
    if cp.returncode:
        raise RuntimeError(
            "Could not start the optional traffic-generator profile: "
            f"{cp.stderr.strip() or cp.stdout.strip()}"
        )
    log.info("Started traffic-generator to produce application logs, metrics, and traces.")
    return True


def stop_traffic_generator(root: Path) -> None:
    """Stop only the optional traffic generator started by a simulator."""
    cp = compose(root, "--profile", "traffic", "stop", "traffic-generator")
    if cp.returncode:
        log.warning("Could not stop traffic-generator: %s", cp.stderr.strip())


def container_environment(cid: str) -> dict[str, str]:
    cp = run(
        ["docker", "inspect", cid, "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        check=False,
    )
    if cp.returncode:
        return {}
    return dict(line.split("=", 1) for line in cp.stdout.splitlines() if "=" in line)


def recreate_order_service(root: Path, version: str, fault_mode: str) -> None:
    cp = compose(
        root,
        "up", "-d", "--force-recreate", "--no-deps", "order-service",
        environment={
            "ORDER_SERVICE_VERSION": version,
            "INCIDENT_ORDER_FAULT_MODE": fault_mode,
        },
    )
    if cp.returncode:
        raise RuntimeError(
            "Could not recreate order-service for the deployment scenario: "
            f"{cp.stderr.strip() or cp.stdout.strip()}"
        )


def wait_for_http(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "unknown error"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Service did not become healthy at {url}: {last_error}")


def configure_dependency_proxy(mode: str, delay_ms: int = 0) -> None:
    payload = json.dumps({"mode": mode, "delay_ms": delay_ms}).encode()
    request = Request(
        "http://localhost:9001/mode",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Dependency proxy returned HTTP {response.status}.")
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not configure dependency proxy: {exc}") from exc


# --------------------------------------------------------------------------- #
# Built-in fault injection API (replaces docker exec approach)
# --------------------------------------------------------------------------- #
SERVICE_PORTS: dict[str, int] = {
    "order-service": 8003,
    "user-service": 8001,
    "product-service": 8002,
}


def _service_base_url(service: str) -> str:
    port = SERVICE_PORTS.get(service, 8003)
    return f"http://localhost:{port}"


def inject_fault(
    service: str,
    mode: str,
    *,
    workers: int = 2,
    megabytes: int = 200,
    duration_seconds: int = 180,
) -> None:
    """Activate a fault via the service's built-in /admin/fault API."""
    url = f"{_service_base_url(service)}/admin/fault"
    body = json.dumps({
        "mode": mode,
        "workers": workers,
        "megabytes": megabytes,
        "duration_seconds": duration_seconds,
    }).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Fault injection returned HTTP {resp.status}")
            result = json.loads(resp.read().decode())
            log.info("Fault injected: %s", result)
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Could not inject fault via {url}: {exc}\n"
            "Make sure the service is running and includes the fault_injection router."
        ) from exc


def clear_fault(service: str) -> None:
    """Clear all active faults via the service's /admin/fault API."""
    url = f"{_service_base_url(service)}/admin/fault"
    req = Request(url, method="DELETE")
    try:
        with urlopen(req, timeout=10) as resp:
            log.info("Faults cleared on %s (HTTP %s)", service, resp.status)
    except (URLError, TimeoutError, OSError) as exc:
        log.warning("Could not clear fault on %s: %s", service, exc)


# --------------------------------------------------------------------------- #
# Legacy docker exec helpers (kept for backward compatibility, prefer the
# built-in fault injection API above for new code)
# --------------------------------------------------------------------------- #
def start_background_python(cid: str, marker: str, source: str) -> None:
    """Run a bounded Python workload in a container and save its PID for recovery."""
    command = f"rm -f {shlex.quote(marker)}; echo $$ > {shlex.quote(marker)}; exec python -c {shlex.quote(source)}"
    cp = exec_in_container(cid, ["sh", "-ec", command], detach=True)
    if cp.returncode:
        raise RuntimeError(f"Could not start workload: {cp.stderr.strip() or cp.stdout.strip()}")


def stop_background_python(cid: str, marker: str) -> None:
    source = (
        "import os, signal, sys\n"
        "root = int(sys.argv[1])\n"
        "children = {}\n"
        "for entry in os.listdir('/proc'):\n"
        "    if not entry.isdigit():\n"
        "        continue\n"
        "    try:\n"
        "        fields = open(f'/proc/{entry}/stat').read().split()\n"
        "        children.setdefault(int(fields[3]), []).append(int(entry))\n"
        "    except (OSError, ValueError, IndexError):\n"
        "        pass\n"
        "pending = [root]\n"
        "descendants = []\n"
        "while pending:\n"
        "    parent = pending.pop()\n"
        "    direct = children.get(parent, [])\n"
        "    descendants.extend(direct)\n"
        "    pending.extend(direct)\n"
        "for pid in reversed(descendants):\n"
        "    try: os.kill(pid, signal.SIGTERM)\n"
        "    except (ProcessLookupError, PermissionError): pass\n"
        "try: os.kill(root, signal.SIGTERM)\n"
        "except (ProcessLookupError, PermissionError): pass\n"
    )
    command = (
        f"if [ -f {shlex.quote(marker)} ]; then "
        f"pid=$(cat {shlex.quote(marker)}); "
        f"python -c {shlex.quote(source)} \"$pid\"; "
        f"rm -f {shlex.quote(marker)}; fi"
    )
    cp = exec_in_container(cid, ["sh", "-ec", command])
    if cp.returncode:
        log.warning("Could not stop workload recorded in %s", marker)


def wait_for_duration(seconds: int, incident_id: str) -> None:
    emit_phase("active", incident_id=incident_id, duration_seconds=seconds)
    time.sleep(seconds)


def observe_baseline(seconds: int, incident_id: str) -> None:
    seconds = max(0, min(seconds, 120))
    emit_phase("baseline", incident_id=incident_id, duration_seconds=seconds)
    time.sleep(seconds)


def observe_recovery(seconds: int, incident_id: str) -> None:
    seconds = max(0, min(seconds, 120))
    emit_phase("recovery_observation", incident_id=incident_id, duration_seconds=seconds)
    time.sleep(seconds)


# --------------------------------------------------------------------------- #
# State guard: makes every incident recoverable even after Ctrl+C / crash
# --------------------------------------------------------------------------- #
STATE_DIR = Path(__file__).resolve().parent / ".state"


@dataclass
class IncidentState:
    incident_id: str
    incident_type: str
    target_service: str
    container_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def path(self) -> Path:
        STATE_DIR.mkdir(exist_ok=True)
        return STATE_DIR / f"{self.incident_type}.json"

    def save(self) -> None:
        self.path().write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.path().unlink()
        except FileNotFoundError:
            pass

    @classmethod
    def load(cls, incident_type: str) -> "IncidentState | None":
        p = STATE_DIR / f"{incident_type}.json"
        if not p.is_file():
            return None
        return cls(**json.loads(p.read_text(encoding="utf-8")))


def finish_recovery(
    root: Path,
    state: IncidentState,
    recovery_seconds: int,
    health_url: str | None = None,
) -> None:
    """Observe recovered traffic, then restore traffic-generator ownership and state."""
    try:
        if health_url:
            wait_for_http(health_url)
        observe_recovery(recovery_seconds, state.incident_id)
    finally:
        if state.extras.get("traffic_started"):
            stop_traffic_generator(root)
        state.clear()


# --------------------------------------------------------------------------- #
# Argparse + graceful shutdown boilerplate
# --------------------------------------------------------------------------- #
def base_argparser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--service", help="Override auto-detected compose service name.")
    p.add_argument("--duration", type=int, default=90,
                   help="Incident duration in seconds (default 90, max 600).")
    p.add_argument("--intensity", type=float, default=1.0,
                   help="Relative intensity (default 1.0).")
    p.add_argument("--baseline-seconds", type=int, default=15,
                   help="Normal-traffic observation window before injection (default 15).")
    p.add_argument("--recovery-seconds", type=int, default=15,
                   help="Normal-traffic observation window after recovery (default 15).")
    p.add_argument("--recover", action="store_true",
                   help="Recover from a previously interrupted run and exit.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print planned actions without executing them.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def clamp_duration(seconds: int, maximum: int = 600) -> int:
    return max(1, min(seconds, maximum))


class GracefulExit:
    """Context manager that always runs cleanup on normal exit, Ctrl+C or SIGTERM."""

    def __init__(self) -> None:
        self._fired = False

    def __enter__(self) -> "GracefulExit":
        def handler(signum, frame):
            if not self._fired:
                self._fired = True
                log.warning("Signal %s received — recovering…", signum)
                raise KeyboardInterrupt
        signal.signal(signal.SIGINT, handler)
        try:
            signal.signal(signal.SIGTERM, handler)
        except (AttributeError, ValueError):
            pass
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is KeyboardInterrupt:
            log.info("Interrupted — cleanup will run.")
            return True
        return False


# --------------------------------------------------------------------------- #
# Pretty status output
# --------------------------------------------------------------------------- #
def banner(incident_id: str, incident_type: str, service: str, phase: str) -> None:
    line = f"[{phase}] {incident_id} ({incident_type}) -> {service}"
    log.info(line)


def emit_phase(phase: str, **kwargs: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "phase": phase,
        **kwargs,
    }
    print(json.dumps(payload), flush=True)
