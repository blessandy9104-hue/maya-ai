"""Emergency stop and conservative resource monitoring for desktop Maya."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from maya_identity.wireframe.math_coordinator import MATH_AGENT, SAFETY_POLICY

ROOT = Path(__file__).parent
STOP_PATH = ROOT / "PRESENCE_STOP"
POLICY_PATH = ROOT / "maya_resource_policy.json"

# Canonical safety policy — owned by the Math Coordination Agent. The on-disk
# policy may only tighten these limits, never relax them.
DEFAULT_POLICY = dict(SAFETY_POLICY)

# Rolling windows consumed by the agent's anomaly detection. The current
# sample is always judged against the prior baseline, never against itself.
# Histories are guarded by a lock because a daemon sampler thread refreshes
# the snapshot cache off the UI thread (see current_snapshot).
_HISTORY_CAP = 64
_history_lock = threading.Lock()
_cpu_history: list[float] = []
_memory_history: list[float] = []
_motion_history: list[float] = []


def _push(history: list[float], value: float) -> None:
    history.append(float(value))
    if len(history) > _HISTORY_CAP:
        del history[:-_HISTORY_CAP]


def record_motion(energy: float) -> dict[str, Any]:
    """Record a per-frame motion-energy sample for instability detection."""
    with _history_lock:
        _push(_motion_history, energy)
        samples = len(_motion_history)
    return {"recorded": True, "motion_samples": samples}


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    memory_percent: float
    maya_process_count: int
    launches_last_minute: int


def load_policy() -> dict[str, Any]:
    try:
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy = dict(DEFAULT_POLICY)
        policy.update(data if isinstance(data, dict) else {})
    except (OSError, ValueError, TypeError):
        policy = dict(DEFAULT_POLICY)
    # Agency: the agent's policy sets the outer bound; disk config may only
    # tighten thresholds, never relax the absolute ceilings.
    for key, ceiling in SAFETY_POLICY.items():
        current = policy.get(key)
        if isinstance(current, (int, float)) and isinstance(ceiling, (int, float)):
            policy[key] = min(current, ceiling)
    return policy


def emergency_stop(reason: str = "manual emergency stop") -> dict[str, Any]:
    STOP_PATH.write_text(f"{reason}\n{time.time()}\n", encoding="utf-8")
    return {"stopped": True, "reason": reason, "marker": str(STOP_PATH)}


def is_stopped() -> bool:
    return STOP_PATH.exists()


def clear_emergency_stop() -> dict[str, Any]:
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    return {"stopped": False, "marker": str(STOP_PATH)}


def evaluate(snapshot: ResourceSnapshot, policy: dict[str, Any] | None = None,
             *, cpu_history: list[float] | None = None,
             memory_history: list[float] | None = None,
             motion_series: list[float] | None = None,
             world_series: list[float] | None = None) -> dict[str, Any]:
    """Safety evaluation, mathematically derived and validated by the agent.

    Plain calls keep the canonical threshold contract (``check_limits``).
    Supplying any of the optional time-series inputs (CPU history, memory
    history, motion series, world series) upgrades the decision to the
    agent's composite :meth:`safety_evaluate`: threshold comparison plus
    variance-based anomaly detection, motion instability, and world-state
    drift — every component bounded by ``clamp01`` and ended by a threshold.
    The returned ``reasons`` list stays a flat list of violation names."""
    policy = policy or load_policy()
    if any(value is not None for value in (
            cpu_history, memory_history, motion_series, world_series)):
        report = MATH_AGENT.safety_evaluate(
            snapshot.cpu_percent,
            snapshot.memory_percent,
            snapshot.maya_process_count,
            snapshot.launches_last_minute,
            stop_active=is_stopped(),
            policy=policy,
            cpu_history=cpu_history,
            memory_history=memory_history,
            motion_series=motion_series,
            world_series=world_series,
        )
        return {"safe": report["safe"], "reasons": report["violations"],
                "checks": report["checks"], "margin": report["margin"],
                "snapshot": asdict(snapshot), "policy": policy}
    report = MATH_AGENT.check_limits(
        snapshot.cpu_percent,
        snapshot.memory_percent,
        snapshot.maya_process_count,
        snapshot.launches_last_minute,
        stop_active=is_stopped(),
        policy=policy,
    )
    return {"safe": report["safe"], "reasons": report["violations"],
            "snapshot": asdict(snapshot), "policy": policy}


# ---- off-thread snapshot sampling ----------------------------------------
# ``psutil.cpu_percent(interval=0.1)`` sleeps ~100 ms. That sleep must never
# run on the tkinter thread, so after the first (synchronous) measurement a
# daemon sampler keeps a fresh cache while the UI reads it without blocking.
# The sample VALUES are the same measurements as before; only the sampling
# thread changed. Safety evaluation logic is untouched.
_SAMPLE_INTERVAL_S = 2.0
_snapshot_lock = threading.Lock()
_snapshot_cache: ResourceSnapshot | None = None
_sampler_started = False
_measuring_proc: Any | None = None


def _component_script(tokens: list[str] | None) -> str | None:
    """Return the Maya component script path in a command line, if any.

    A Maya component is a Python module launched from the project root whose
    stem is a Maya module (``maya_*``, ``presence``, ``assistant``).
    Matching on the resolved module path keeps the metric scoped to Maya
    itself: an unrelated process whose command line merely contains the
    string "maya" (for example a shell opened inside the project folder) is
    not a Maya component."""
    if not tokens:
        return None
    try:
        root = ROOT.resolve()
    except OSError:
        return None
    for token in tokens:
        if not token.lower().endswith(".py"):
            continue
        path = Path(token)
        try:
            if path.parent.resolve() != root:
                continue
        except OSError:
            continue
        stem = path.stem.lower()
        if "maya" in stem or stem in {"presence", "assistant"}:
            return str(path)
    return None


def _maya_components(*, include_children: bool = True) -> list[Any]:
    """Processes running an in-project Maya component via the interpreter.

    ``include_children=False`` returns only *independent* Maya components:
    an entry is counted unless one of its ancestors in the process tree is
    itself a Maya component. This keeps the App shell and its persistent
    chat engine, plus the service worker and its own engine child, inside
    one deployment — while a second app instance or a stray/duplicate
    worker (whose parent is not Maya) is still counted. The ``max_process
    _count`` runaway guard therefore keeps working unchanged."""
    import psutil
    items: list[Any] = []
    for item in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        if _component_script(item.info.get("cmdline")) is None:
            continue
        items.append(item)
    if include_children:
        return items
    maya_pids = {item.info["pid"] for item in items}
    return [item for item in items
            if item.info.get("ppid") not in maya_pids]


def _collect_snapshot() -> ResourceSnapshot | None:
    """Local process metrics; fail closed on error. May run on the sampler
    thread.

    The sampled CPU is the caller's own process total averaged over the
    non-blocking window since the previous reading (the sampler cadence), so
    snapshots reflect the process's long-run rate rather than a 100 ms slice;
    the anomaly evaluation then sees a smooth, representative series.
    Memory is the Maya component set's own resident set size as a percentage
    of installed RAM — the resource Maya itself consumes, matching the
    process-local CPU metric and the Maya-scoped process count."""
    try:
        import psutil
        global _measuring_proc
        if _measuring_proc is None:
            _measuring_proc = psutil.Process(os.getpid())
        cpu = _measuring_proc.cpu_percent(interval=None)
        components = _maya_components()
        total_ram = psutil.virtual_memory().total
        rss_sum = sum(item.memory_info().rss for item in components)
        memory = (rss_sum / total_ram * 100.0) if total_ram > 0 else 0.0
        maya_count = len(_maya_components(include_children=False))
        return ResourceSnapshot(cpu, memory, maya_count, 0)
    except Exception:
        return None


def _sampler_loop() -> None:
    global _snapshot_cache
    while True:
        time.sleep(_SAMPLE_INTERVAL_S)
        sample = _collect_snapshot()
        if sample is not None:
            with _snapshot_lock:
                _snapshot_cache = sample


def current_snapshot() -> ResourceSnapshot | None:
    """Return the latest local-process snapshot without blocking the caller.

    The first call measures synchronously (identical cost and result to the
    original implementation). Afterwards a daemon sampler refreshes the cache
    on its own thread so the tkinter loop never blocks on psutil; the UI
    thread only reads the cached ResourceSnapshot. If psutil is unavailable
    the monitor fails closed (returns None), as before.
    """
    global _snapshot_cache, _sampler_started
    with _snapshot_lock:
        if _snapshot_cache is not None:
            return _snapshot_cache
        sample = _collect_snapshot()
        if sample is None:
            return None
        _snapshot_cache = sample
        if not _sampler_started:
            _sampler_started = True
            threading.Thread(target=_sampler_loop,
                             name="maya-resource-sampler",
                             daemon=True).start()
        return sample


def status() -> dict[str, Any]:
    snapshot = current_snapshot()
    if snapshot is None:
        return {"safe": False, "monitor_available": False, "reason": "resource monitor unavailable; fail closed"}
    with _history_lock:
        _push(_cpu_history, snapshot.cpu_percent)
        _push(_memory_history, snapshot.memory_percent)
        motion = list(_motion_history) or None
        cpu_baseline = list(_cpu_history[:-1])
        memory_baseline = list(_memory_history[:-1])
    world = None
    try:
        from maya_world_model import numeric_uncertainty_series
        world = numeric_uncertainty_series() or None
    except Exception:
        world = None
    result = evaluate(
        snapshot,
        cpu_history=cpu_baseline,
        memory_history=memory_baseline,
        motion_series=motion,
        world_series=world,
    )
    result["monitor_available"] = True
    return result


if __name__ == "__main__":
    print(json.dumps(status(), indent=2, ensure_ascii=False))
