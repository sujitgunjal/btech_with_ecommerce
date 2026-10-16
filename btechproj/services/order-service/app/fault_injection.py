"""
Built-in fault injection for chaos engineering.

Instead of injecting faults via ``docker exec`` (unreliable, platform-dependent),
this module lets the application simulate its own resource failures through an
HTTP admin API.

Supported fault modes
---------------------
  cpu     – Spawn CPU-burning daemon threads inside the app process.
  memory  – Allocate a configurable block of resident memory.
  none    – Clear all active faults (the default/recovery state).

Every injected fault carries a *duration_seconds* safety net: if the calling
script crashes without cleaning up, the fault auto-clears after that deadline.

API surface (mounted at ``/admin``)
-----------------------------------
  POST   /admin/fault   – Activate a fault (JSON body with mode + parameters).
  GET    /admin/fault   – Query the current fault state.
  DELETE /admin/fault   – Immediately clear all active faults.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("order-service.fault")
router = APIRouter(prefix="/admin", tags=["fault-injection"])

# ------------------------------------------------------------------ #
# Global mutable fault state (guarded by _lock)
# ------------------------------------------------------------------ #
_lock = threading.Lock()

_state: dict = {
    "mode": "none",
    "cpu_stop_events": [],
    "cpu_threads": [],
    "memory_block": None,
    "memory_mb": 0,
    "auto_clear_timer": None,
    "activated_at": None,
}


# ------------------------------------------------------------------ #
# Pydantic models
# ------------------------------------------------------------------ #
class FaultRequest(BaseModel):
    mode: str = Field(
        ...,
        pattern="^(none|cpu|memory)$",
        description="Fault type to inject: none | cpu | memory",
    )
    workers: int = Field(
        default=2, ge=1, le=8,
        description="Number of CPU-burning threads (cpu mode only).",
    )
    megabytes: int = Field(
        default=200, ge=16, le=512,
        description="Memory to allocate in MiB (memory mode only).",
    )
    duration_seconds: int = Field(
        default=180, ge=10, le=660,
        description="Safety-net auto-clear timeout.",
    )


class FaultStatus(BaseModel):
    mode: str
    cpu_threads_active: int = 0
    memory_allocated_mb: int = 0
    activated_at: Optional[float] = None


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #
def _cpu_burn(stop: threading.Event) -> None:
    """Pure-Python busy loop — runs until *stop* is set."""
    v = 1
    while not stop.is_set():
        for _ in range(200_000):
            v = (v * 1664525 + 1013904223) & 0xFFFFFFFF
        # Check stop flag every ~200k iterations so the thread
        # exits within a fraction of a second when asked.


def _clear_all() -> None:
    """Idempotently tear down any active fault."""
    with _lock:
        # Cancel safety-net timer
        timer = _state["auto_clear_timer"]
        if timer is not None:
            timer.cancel()
            _state["auto_clear_timer"] = None

        # Stop CPU threads
        for ev in _state["cpu_stop_events"]:
            ev.set()
        for t in _state["cpu_threads"]:
            t.join(timeout=5)
        _state["cpu_stop_events"].clear()
        _state["cpu_threads"].clear()

        # Release memory
        _state["memory_block"] = None
        _state["memory_mb"] = 0

        _state["mode"] = "none"
        _state["activated_at"] = None

    logger.info("All faults cleared.")


def _schedule_auto_clear(seconds: int) -> None:
    """Start a daemon timer that calls ``_clear_all`` after *seconds*."""
    timer = threading.Timer(seconds, _clear_all)
    timer.daemon = True
    timer.start()
    _state["auto_clear_timer"] = timer


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #
@router.post("/fault", response_model=FaultStatus)
def inject_fault(req: FaultRequest):
    """Activate a fault mode. Any previously active fault is cleared first."""
    _clear_all()

    if req.mode == "none":
        return _build_status()

    with _lock:
        _state["mode"] = req.mode
        _state["activated_at"] = time.time()

        if req.mode == "cpu":
            for _ in range(req.workers):
                ev = threading.Event()
                t = threading.Thread(target=_cpu_burn, args=(ev,), daemon=True)
                t.start()
                _state["cpu_stop_events"].append(ev)
                _state["cpu_threads"].append(t)
            logger.warning(
                "CPU fault injected: %d worker threads for up to %ds",
                req.workers, req.duration_seconds,
            )

        elif req.mode == "memory":
            block = bytearray(req.megabytes * 1024 * 1024)
            # Touch every page so the OS actually commits the memory.
            for offset in range(0, len(block), 4096):
                block[offset] = 1
            _state["memory_block"] = block
            _state["memory_mb"] = req.megabytes
            logger.warning(
                "Memory fault injected: %d MiB for up to %ds",
                req.megabytes, req.duration_seconds,
            )

        _schedule_auto_clear(req.duration_seconds)

    return _build_status()


@router.get("/fault", response_model=FaultStatus)
def get_fault_status():
    """Return the current fault state."""
    return _build_status()


@router.delete("/fault", response_model=FaultStatus)
def clear_fault():
    """Immediately clear all active faults."""
    _clear_all()
    return _build_status()


def _build_status() -> FaultStatus:
    with _lock:
        return FaultStatus(
            mode=_state["mode"],
            cpu_threads_active=len(_state["cpu_threads"]),
            memory_allocated_mb=_state["memory_mb"],
            activated_at=_state["activated_at"],
        )
