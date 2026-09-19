"""Controlled-condition runner: sweeps suites and launches the runtime.

Each suite runs in its own subprocess (isolated, script-style, cwd = project
root) with stdout/stderr captured. Anomalies are detected deterministically:
non-zero exit, tracebacks, non-``=OK`` output, empty output, or excessive run
time. The controlled runtime launch compares a deterministic math signature
across a headless and a normal interpreter to prove device-independence.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

from .manifest import CONTROLLED_RUNTIME, SUITE_CONTRACTS, SUITES

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PYTHON = sys.executable
DEFAULT_TIMEOUT_MS = 300000


def _parse_ok_labels(stdout):
    return sum(1 for line in stdout.splitlines()
               if line.strip().endswith("=OK"))


_BENIGN_EXACT = {"DECISION RECORDED"}
_BENIGN_PREFIXES = ("status=", "exit=", "runtime_profile=", "profile=")

# Contradictory status lines can never be treated as normal output. A suite
# that literally prints a failure verdict (while exiting 0) is anomalous.
_NEGATION_TOKENS = {
    "clean=false", "clean=0", "passed=false", "passed=0", "pass=false",
    "ready=false", "ready=0", "ok_total=0", "status=failed", "status=error",
    "failed=true", "exit=1",
}

# Category markers carry real evidence: a suite prints one of these (in a
# failing run) to say which boundary was crossed. They are only honored when
# the suite already produced a failure, so passing suites that merely mention
# a category are never misclassified.
_CATEGORY_MARKERS = {
    "safety_boundary_violation": ("safety_boundary_violation",
                                  "safety boundary violation"),
    "rendering_anomaly": ("rendering_anomaly", "rendering anomaly"),
}


def _is_ok_output_line(line):
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.lower() in _NEGATION_TOKENS:
        return False
    if stripped.endswith("=OK"):
        return True
    if stripped in _BENIGN_EXACT:
        return True
    if any(stripped.startswith(prefix) for prefix in _BENIGN_PREFIXES):
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", stripped):  # key=value summaries
        return True
    if stripped.startswith("{") or stripped.startswith("}"):
        return True
    if re.match(r'^\s*"[A-Za-z_]+":', stripped):  # JSON member lines
        return True
    if stripped[0] in "{}[],\"":  # remaining JSON structural lines
        return True
    return False


def _anomalies_from_output(stdout, stderr, returncode, duration_s):
    anomalies = []
    if not stdout.strip():
        anomalies.append({"kind": "unexpected_output",
                          "detail": "empty output"})
    if returncode != 0:
        anomalies.append({"kind": "unintended_behavior",
                          "detail": f"suite exited {returncode}"})
    if "Traceback" in stdout or "Traceback" in stderr:
        anomalies.append({"kind": "unexpected_output",
                          "detail": "traceback present in output"})
    if "Error" in stderr or "Exception" in stderr:
        anomalies.append({"kind": "unexpected_output",
                          "detail": "exception text present in stderr"})
    unexpected = [line for line in stdout.splitlines()
                  if not _is_ok_output_line(line)]
    if unexpected:
        anomalies.append({"kind": "unexpected_output",
                          "detail": "unexpected output lines",
                          "lines": unexpected[:8]})
    duration_ms = duration_s * 1000.0
    if duration_ms > DEFAULT_TIMEOUT_MS:
        anomalies.append({"kind": "timing_irregularity",
                          "detail": f"duration {duration_ms:.0f} ms exceeds deadline"})
    if anomalies:
        combined = (stdout + "\n" + stderr).lower()
        for _kind, _markers in _CATEGORY_MARKERS.items():
            if any(_marker in combined for _marker in _markers):
                anomalies.append({"kind": _kind,
                                  "detail": "explicit marker identifies " + _kind})
    return anomalies


def run_suite(filename, python=None, cwd=None, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Run one suite in controlled isolation and return the observed record."""
    start = time.perf_counter()
    proc = subprocess.run(
        [python or DEFAULT_PYTHON, filename],
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        timeout=max(timeout_ms / 1000.0, 1.0),
    )
    return _record(filename, proc, start)


def _record(filename, proc, start):
    duration_s = time.perf_counter() - start
    anomalies = _anomalies_from_output(
        proc.stdout, proc.stderr, proc.returncode, duration_s
    )
    ok_labels = _parse_ok_labels(proc.stdout)
    contract = SUITE_CONTRACTS.get(pathlib.Path(str(filename)).name)
    if contract is not None and contract["expected_ok"] != ok_labels:
        anomalies.append({"kind": "unexpected_output",
                          "detail": f"ok evidence mismatch: expected "
                                    f"{contract['expected_ok']}, saw {ok_labels}"})
    return {
        "suite": filename,
        "ok_labels": ok_labels,
        "returncode": proc.returncode,
        "duration_s": round(duration_s, 3),
        "anomalies": anomalies,
        "clean": not anomalies,
    }


def sweep(suites=SUITES, python=None, cwd=None, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Run the full (or given) battery under controlled conditions."""
    results = []
    for filename in suites:
        start = time.perf_counter()
        python_bin = python or DEFAULT_PYTHON
        try:
            proc = subprocess.run(
                [python_bin, filename],
                capture_output=True,
                text=True,
                cwd=str(cwd or PROJECT_ROOT),
                timeout=max(timeout_ms / 1000.0, 1.0),
            )
            results.append(_record(filename, proc, start))
        except subprocess.TimeoutExpired:
            duration_s = time.perf_counter() - start
            results.append({
                "suite": filename,
                "ok_labels": 0,
                "returncode": None,
                "duration_s": round(duration_s, 3),
                "anomalies": [{"kind": "timing_irregularity",
                               "detail": f"suite timed out after "
                                         f"{timeout_ms} ms"}],
                "clean": False,
            })
    any_anomaly = any(r["anomalies"] for r in results)
    return {
        "approach": "external",
        "suites": results,
        "suite_count": len(results),
        "ok_total": sum(r["ok_labels"] for r in results),
        "clean": not any_anomaly,
    }


def _signature_exprs():
    """The exact operations computed by both the native and headless arms,
    in a single order-of-operations source so neither arm can drift."""
    return (
        "round(a.pattern_state(0.0, 1.0, 0.5), 15)",
        "round(rt.core.cosine_similarity((1.0, 0.0), (1.0, 0.0)), 15)",
        "round(a.world_stability([1.0, 1.0, 1.0, 1.0], max_std=0.05)['std'], 15)",
        "len(rt.core.CHANNEL_MAX)",
    )


def _signature():
    """Deterministic cross-device math signature from the runtime core."""
    import maya_runtime as rt

    agent = rt.MATH_AGENT
    namespace = {"rt": rt, "a": agent, "round": round, "len": len}
    return tuple(eval(expr, namespace) for expr in _signature_exprs())


def launch_runtime(python=None):
    """Launch the runtime in controlled conditions; verify device-invariance."""
    python = python or DEFAULT_PYTHON
    anomalies = []
    try:
        native = _signature()
    except Exception as exc:
        anomalies.append({"kind": "unintended_behavior",
                          "detail": f"native runtime launch failed: {exc!r}"})
        native = None
    headless_code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import maya_runtime as rt\n"
        "a = rt.MATH_AGENT\n"
        "sig = (%s)\n"
        "print(repr(sig))\n"
    ) % (str(PROJECT_ROOT), ", ".join(_signature_exprs()))
    env = dict(os.environ)
    env[CONTROLLED_RUNTIME["headless_env"]] = "1"
    start = time.perf_counter()
    proc = subprocess.run(
        [python, "-c", headless_code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        timeout=60.0,
    )
    duration_s = time.perf_counter() - start
    headless = None
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            headless = eval(proc.stdout.strip().splitlines()[-1])
        except Exception as exc:
            anomalies.append({"kind": "unexpected_output",
                              "detail": f"unparsable headless signature: {exc!r}"})
    if proc.returncode != 0:
        anomalies.append({"kind": "unintended_behavior",
                          "detail": "headless launch failed",
                          "stderr": proc.stderr[:400]})
    elif headless is None:
        anomalies.append({"kind": "unexpected_output",
                          "detail": "headless signature missing"})
    elif not (isinstance(headless, tuple) and len(headless) == 4
              and all(isinstance(v, (int, float)) for v in headless)):
        anomalies.append({"kind": "unexpected_output",
                          "detail": f"signature shape invalid: {headless!r}"})
    if native is not None and headless is not None and native != headless:
        anomalies.append({"kind": "instability_drift",
                          "detail": f"native {native} != headless {headless}"})
    if len(CONTROLLED_RUNTIME["signature_ops"]) != 4:
        anomalies.append({"kind": "unintended_behavior",
                          "detail": "controlled signature definition drifted"})
    return {
        "approach": "external",
        "launch": "controlled_runtime",
        "signature_native": native,
        "signature_headless": headless,
        "duration_s": round(duration_s, 3),
        "anomalies": anomalies,
        "clean": not anomalies,
    }