"""Read-only runtime device self-knowledge for Maya.

Lets Maya describe, honestly and bounded, the local machine it runs on:
a small profile that fails closed when introspection is unavailable. It
never writes, never probes peripherals, never reads private paths, and
justifies no action on its own — it is descriptive context for the
capability self-report and the runtime loop.

Everything non-deterministic (memory pressure) is read once per call and
reported as the snapshot it was; the structural fields (platform, CPU
count, Python version) are constants for a given host.
"""
from __future__ import annotations

from typing import Any

DEVICE_CLASS_DEFAULT = "local_pc"


def detect() -> dict[str, Any]:
    """Return the bounded device profile, failing closed on every probe.

    Fields: os_name, machine, python_version, cpu_count, memory,
    device_class, fail_closed (reason when any probe degraded).
    """
    import platform
    profile: dict[str, Any] = {
        "os_name": None,
        "machine": None,
        "python_version": None,
        "cpu_count": None,
        "memory": None,
        "device_class": DEVICE_CLASS_DEFAULT,
        "fail_closed": None,
    }
    try:
        profile["os_name"] = platform.system() or None
    except Exception:
        pass
    try:
        profile["machine"] = platform.machine() or None
    except Exception:
        pass
    try:
        profile["python_version"] = platform.python_version() or None
    except Exception:
        pass
    try:
        profile["cpu_count"] = int(os_cpu_count() or 0)
        if profile["cpu_count"] <= 0:
            profile["cpu_count"] = None
    except Exception:
        profile["cpu_count"] = None
    profile["memory"] = _memory_snapshot()
    profile["device_class"] = DEVICE_CLASS_DEFAULT
    degraded = [key for key in ("os_name", "cpu_count")
                if profile[key] is None]
    if degraded:
        profile["fail_closed"] = (
            "introspection unavailable for: " + ", ".join(degraded))
    return profile


def _cpu_count() -> int | None:
    import os
    try:
        return os.cpu_count()
    except Exception:
        return None


def _memory_snapshot() -> dict[str, Any] | None:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total_bytes": int(vm.total),
            "available_bytes": int(vm.available),
            "percent_used": round(float(vm.percent), 1),
            "resource": "psutil",
        }
    except Exception:
        return None


def os_cpu_count() -> int | None:
    """Visible for tests and callers that want just the CPU count."""
    return _cpu_count()


def local_capability_groups() -> list[str]:
    """Registered capability groups that work without the model or network.

    Derived from the single registry's degraded-safe set, so this cannot
    drift from what Maya actually advertises offline.
    """
    from maya_capabilities import degraded_groups
    return sorted(degraded_groups())


def model_dependent_groups() -> list[str]:
    """Registered capability groups the offline-safe rule treats as needing
    the model or live research: every registered group that is not in the
    degraded-safe set. A clean partition of the registry, so no group can be
    silently unclassified."""
    from maya_capabilities import CAPABILITY_REGISTRY
    return sorted({name for name, _, _ in CAPABILITY_REGISTRY}
                  - set(local_capability_groups()))


def suitability() -> dict[str, Any]:
    """Honest local-suitability classification of the capability groups."""
    return {
        "device_class": DEVICE_CLASS_DEFAULT,
        "local_capability_groups": local_capability_groups(),
        "model_dependent_groups": model_dependent_groups(),
        "note": "groups are partitioned by the registry's offline-safe rule: "
                "local groups work without the model; every other registered "
                "group is treated as model- or research-dependent.",
    }


def summary() -> str:
    """Compact textual self-description for the chat command surface."""
    import json as _json
    profile = detect()
    return ("[device profile]\n"
            "system: {os} | machine: {machine} | python: {python}\n"
            "cpu cores: {cpu} | memory: {memory}\n"
            "local-groups: {local}\n"
            "model/network-groups: {dependent}\n").format(
        os=profile["os_name"], machine=profile["machine"],
        python=profile["python_version"], cpu=profile["cpu_count"],
        memory=_json.dumps(profile["memory"]) if profile["memory"] else "unavailable",
        local=", ".join(local_capability_groups()),
        dependent=", ".join(model_dependent_groups()))