"""Stabilization report: the external verification deliverable.

Aggregates the sweep and controlled launch into the six required monitoring
categories (unintended behavior, unexpected output, instability/drift,
rendering anomalies, safety violations, timing irregularities) and yields a
single ``clean`` verdict consumed by the readiness decision.
"""
from __future__ import annotations

from .manifest import CONTROLLED_RUNTIME
from .runner import launch_runtime, sweep

CATEGORIES = (
    ("unintended_behavior", "unintended behavior"),
    ("unexpected_output", "unexpected output"),
    ("instability_drift", "instability or drift"),
    ("rendering_anomaly", "rendering anomalies"),
    ("safety_boundary_violation", "safety boundary violations"),
    ("timing_irregularity", "timing irregularities"),
)


def _category_counts(sweep_result, launch_result):
    counts = {}
    for kind, _label in CATEGORIES:
        n = sum(1 for suite in sweep_result["suites"]
                for anomaly in suite["anomalies"]
                if anomaly["kind"] == kind)
        n += sum(1 for anomaly in launch_result["anomalies"]
                 if anomaly["kind"] == kind)
        counts[kind] = n
    return counts


def stabilization_report(sweep_result=None, launch_result=None):
    sweep_result = sweep_result if sweep_result is not None else sweep()
    launch_result = launch_result if launch_result is not None else launch_runtime()

    suite_anomalies = [suite["suite"] for suite in sweep_result["suites"]
                       if suite["anomalies"]]
    counts = _category_counts(sweep_result, launch_result)
    clean = (sweep_result["clean"]
             and launch_result["clean"]
             and not suite_anomalies
             and all(count == 0 for count in counts.values()))

    return {
        "report": "stabilization",
        "approach": "external",
        "clean": clean,
        "categories": counts,
        "suites_clean": sweep_result["clean"],
        "suites_with_anomalies": suite_anomalies,
        "launch_clean": launch_result["clean"],
        "signature_native": launch_result["signature_native"],
        "signature_headless": launch_result["signature_headless"],
        "controlled_launch": CONTROLLED_RUNTIME["module"],
        "decision": "ready_condition_met" if clean else "not_cleared",
    }