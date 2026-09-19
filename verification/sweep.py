"""Console entry point: python -m verification.sweep.

Runs the full external verification under one ``run_nonce``, records every
anomaly and the external verdict into the verification monitor, produces the
stabilization report, and -- if clean -- confirms the external verdict so the
dual-path readiness condition can be met.
"""
from __future__ import annotations

import json
import secrets

from . import authenticity
from . import manifest
from . import monitor
from .report import stabilization_report
from .runner import launch_runtime, sweep


def main(python=None):
    from maya_identity import stabilization

    # Per-run ephemeral authenticating key, installed into both monitor and
    # stabilization so the recorded verdict is signed and confirm() accepts
    # only that run's authenticated verdict. Held in memory for the record ->
    # confirm window; never persisted or logged.
    key = authenticity.fresh_key()
    monitor.set_verdict_key(key)
    stabilization.set_verdict_key(key)

    nonce = secrets.token_hex(8)
    print(f"[verify] protocol manifest: {len(manifest.SUITES)} suites "
          f"(module={manifest.CONTROLLED_RUNTIME['module']}) run={nonce}")
    result = sweep(python=python)
    launch = launch_runtime(python=python)
    report = stabilization_report(result, launch)
    report = dict(report)
    report["run_nonce"] = nonce
    report["suite_count"] = result["suite_count"]
    report["ok_total"] = result["ok_total"]
    report["protocol"] = stabilization.PROTOCOL_VERSION

    evidence = {
        suite["suite"]: {
            "returncode": suite.get("returncode", -1),
            "ok_labels": suite.get("ok_labels", 0),
        }
        for suite in result["suites"]
    }
    report["evidence"] = authenticity.evidence_digest(evidence)

    for suite in result["suites"]:
        for anomaly in suite["anomalies"]:
            monitor.record(anomaly["kind"], anomaly["detail"],
                           source="external", run_nonce=nonce)
    for anomaly in launch["anomalies"]:
        monitor.record(anomaly["kind"], anomaly["detail"],
                       source="controlled_launch", run_nonce=nonce)

    print(f"[verify] sweep: {result['suite_count']} suites, "
          f"{result['ok_total']} ok-labels, clean={result['clean']}")
    for suite in result["suites"]:
        state = "OK" if suite["clean"] else "ANOMALY"
        print(f"  {state:<7} {suite['suite']:<38} "
              f"ok={suite['ok_labels']:<3} {suite['duration_s']:>6.2f}s")
        for anomaly in suite["anomalies"]:
            print(f"         -> {anomaly['kind']}: {anomaly['detail']}")
    print(f"[verify] controlled launch: clean={launch['clean']} "
          f"native={launch['signature_native']} "
          f"headless={launch['signature_headless']}")
    print(f"[verify] stabilization report: clean={report['clean']} "
          f"categories={report['categories']}")

    if report["clean"]:
        monitor.record_verdict(nonce, report["clean"],
                               report["suite_count"], report["ok_total"],
                               protocol=report["protocol"],
                               evidence=evidence)
        decision = stabilization.confirm(report)
        print("[verify] external verdict recorded -> "
              f"ready={stabilization.is_ready()} state={stabilization.state()['status']}")
        print("[verify] READY" if stabilization.is_ready() else "[verify] NOT READY")
        return 0
    print("[verify] NOT READY (external verification not clean)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())